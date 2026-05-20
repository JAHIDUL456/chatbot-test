import logging
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.insight import InsightRequest, InsightResponse, AnalyticsSummary
from app.services.groq_client import groq_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/generate-insight",
    response_model=InsightResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Shop Business Insights",
    description=(
        "Processes sales and stock data locally, calculates key retail metrics "
        "(total revenue, low stock, top product, dead stock), and leverages Groq LLM "
        "to output tailored business insights and actionable suggestions in Bengali."
    )
)
async def generate_insight(request: InsightRequest) -> InsightResponse:
    """
    POST /generate-insight
    1. Performs calculations (revenue, top products, low stock, dead stock) in Python.
    2. Constructs a compact summary (no raw sales or stock data).
    3. Calls Groq using llama-3.1-8b-instant.
    4. Returns Bengali insights and structured analytics.
    """
    try:
        logger.info(f"Processing insight request for shop: '{request.shop_name}' over period: '{request.period}'")

        # 1. Group sales by product to aggregate revenue and quantity
        product_sales_revenue = {}
        product_sales_qty = {}
        for item in request.sales:
            p = item.product
            product_sales_revenue[p] = product_sales_revenue.get(p, 0.0) + item.revenue
            product_sales_qty[p] = product_sales_qty.get(p, 0.0) + item.qty

        # 2. Total revenue and total quantity sold
        total_revenue = sum(item.revenue for item in request.sales)
        total_qty = sum(item.qty for item in request.sales)

        # 3. Top selling product by quantity sold
        if product_sales_qty:
            top_product = max(product_sales_qty, key=lambda k: product_sales_qty[k])
        else:
            top_product = "None"

        # 4. Product ranking by revenue (sorting descending)
        sorted_by_revenue = sorted(product_sales_revenue.items(), key=lambda x: x[1], reverse=True)
        revenue_ranking_str = ", ".join([f"{p} ({r:.2f})" for p, r in sorted_by_revenue[:5]])

        # 5. Group stock by product to handle any duplicate entries
        product_stock_levels = {}
        for item in request.stock:
            p = item.product
            product_stock_levels[p] = product_stock_levels.get(p, 0.0) + item.remaining

        # 6. Low stock products (remaining < 10)
        low_stock_products = [p for p, rem in product_stock_levels.items() if rem < 10]

        # 7. Dead stock detection (remaining > 0 but has 0 sales in the period)
        dead_stock_products = []
        for p, rem in product_stock_levels.items():
            if rem > 0:
                # If product had no recorded sales (revenue is 0 or not in sales list)
                if product_sales_revenue.get(p, 0.0) == 0.0:
                    dead_stock_products.append(p)

        logger.debug(
            f"Calculated Analytics - Revenue: {total_revenue}, Qty: {total_qty}, "
            f"Top Product: {top_product}, Low Stock Count: {len(low_stock_products)}, "
            f"Dead Stock Count: {len(dead_stock_products)}"
        )

        # 8. Prepare compact summary prompt for LLM (no raw sales or stock logs)
        low_stock_str = ", ".join(low_stock_products) if low_stock_products else "None"
        dead_stock_str = ", ".join(dead_stock_products) if dead_stock_products else "None"

        system_instruction = (
            "You are a professional, friendly, and expert retail consultant speaking fluent Bengali. "
            "Your objective is to provide a brief, high-value, and actionable business report for a shopkeeper. "
            "You must write exclusively in Bengali (বাংলা). Do not translate the business metrics names into english characters, "
            "but present your recommendations, trend predictions, and stock suggestions clearly. "
            "Keep the output clean and structure it into four distinct sections: "
            "1. ব্যবসার অবস্থা বিশ্লেষণ (Business Insights), "
            "2. ইনভেন্টরি বা স্টক উন্নত করার পরামর্শ (Stock Suggestions), "
            "3. ভবিষ্যৎ বিক্রয়ের গতিধারা বা ট্রেন্ড (Future Trends), "
            "4. দোকানদারের জন্য সরাসরি পালনযোগ্য পরামর্শ (Actionable Advice)."
        )

        user_content = (
            f"দোকানের নাম (Shop Name): {request.shop_name}\n"
            f"সময়কাল (Period): {request.period}\n"
            f"মোট রাজস্ব (Total Revenue): ৳{total_revenue:.2f}\n"
            f"সবচেয়ে বেশি বিক্রি হওয়া পণ্য (Top Selling Product): {top_product}\n"
            f"রাজস্ব অনুযায়ী শীর্ষ পণ্যসমূহ (Top Revenue Products): {revenue_ranking_str if revenue_ranking_str else 'None'}\n"
            f"কম স্টক থাকা পণ্য (Low Stock Products - < 10 units): {low_stock_str}\n"
            f"অচল বা অবিক্রীত স্টক (Dead Stock - has inventory but 0 sales): {dead_stock_str}\n\n"
            "অনুগ্রহ করে উপরোক্ত তথ্য বিশ্লেষণ করে নিম্নলিখিত বিষয়গুলো বাংলায় প্রদান করুন:\n"
            "- ব্যবসার সার্বিক অবস্থার বিশ্লেষণ (Bengali business insights)\n"
            "- স্টক বা ইনভেন্টরি উন্নত করার পরামর্শ (Stock improvement suggestions)\n"
            "- ভবিষ্যৎ বিক্রয়ের ট্রেন্ড বা গতিধারার পূর্বাভাস (Predict future sales trend)\n"
            "- দোকানদারের জন্য সরাসরি পালনযোগ্য ও বাস্তবসম্মত পরামর্শ (Actionable advice for shopkeeper)"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        # 9. Invoke Groq completion service with llama-3.1-8b-instant, fallback if blocked/rate-limited
        model_name = "llama-3.1-8b-instant"
        try:
            ai_insight_text, _ = await groq_service.generate_chat_completion(
                messages=messages,
                temperature=0.7,
                model=model_name
            )
        except Exception as api_err:
            logger.warning(
                f"Failed to generate insight using model {model_name}. "
                f"Attempting fallback to configured default model '{settings.GROQ_MODEL}'... "
                f"Error: {api_err}"
            )
            model_name = settings.GROQ_MODEL
            ai_insight_text, _ = await groq_service.generate_chat_completion(
                messages=messages,
                temperature=0.7,
                model=model_name
            )

        # 10. Construct response matching the required structure
        analytics_summary = AnalyticsSummary(
            total_revenue=total_revenue,
            top_product=top_product,
            low_stock=low_stock_products
        )

        return InsightResponse(
            success=True,
            analytics=analytics_summary,
            ai_insight_bn=ai_insight_text,
            model=model_name
        )

    except Exception as e:
        logger.error(f"Failed to generate shop insights: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}"
        )
