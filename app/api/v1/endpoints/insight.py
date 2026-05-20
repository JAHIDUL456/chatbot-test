import logging
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.insight import InsightRequest, InsightResponse, AnalyticsSummary
from app.services.groq_client import groq_service
from app.services.insight_cache import insight_cache

logger = logging.getLogger(__name__)
router = APIRouter()


def generate_local_fallback_insights(
    shop_name: str,
    period: str,
    total_revenue: float,
    top_product: str,
    low_stock: list,
    dead_stock: list
) -> str:
    """
    Generates high-quality, readable business insights and advice in Bengali locally.
    Acts as a fail-safe fallback when Groq LLM API limits are exhausted or connection fails.
    """
    # 1. Business Insights
    insights = f"### ব্যবসার অবস্থা বিশ্লেষণ\n\nগত {period}-এ '{shop_name}' এর মোট বিক্রি থেকে অর্জিত রাজস্ব ছিল ৳{total_revenue:,.2f}। "
    if top_product and top_product != "None":
        insights += f"এই সময়ে সবচেয়ে জনপ্রিয় ও বিক্রির শীর্ষে থাকা পণ্য ছিল '{top_product}'। "
    
    if dead_stock:
        insights += f"তবে দোকানে কিছু অচল স্টক ({', '.join(dead_stock[:3])}) রয়েছে যা এসময়ে বিক্রি হয়নি। "
    else:
        insights += "দোকানের সব পণ্যই নিয়মিত কম-বেশি বিক্রি হচ্ছে।"
        
    # 2. Stock Suggestions
    insights += "\n\n### ইনভেন্টরি বা স্টক উন্নত করার পরামর্শ\n\n"
    if low_stock:
        insights += f"* কম স্টক থাকা পণ্যগুলোর ({', '.join(low_stock[:3])}) স্টক লেভেল ১০ এর নিচে নেমে গেছে। গ্রাহক হারানোর আগে দ্রুত এগুলো পুনরায় সংগ্রহ করুন।\n"
    if dead_stock:
        insights += f"* অবিক্রীত বা অচল স্টকগুলোর ({', '.join(dead_stock[:3])}) জন্য বিশেষ মূল্যছাড় বা আকর্ষণীয় অফার দিয়ে দ্রুত ক্লিয়ার করার ব্যবস্থা নিন।\n"
    if not low_stock and not dead_stock:
        insights += "* আপনার ইনভেন্টরি ব্যালেন্স সন্তোষজনক। নিয়মিত স্টকের পরিমাণ পর্যবেক্ষণ করুন।\n"

    # 3. Future Trends
    insights += "\n### ভবিষ্যৎ বিক্রয়ের গতিধারা বা ট্রেন্ড\n\n"
    if top_product and top_product != "None":
        insights += f"* আগামী দিনগুলোতেও '{top_product}' এর জোরালো চাহিদা অব্যাহত থাকার প্রবল সম্ভাবনা রয়েছে। পর্যাপ্ত স্টক প্রস্তুত রাখুন।\n"
    insights += "* আসন্ন দিনগুলোতে ক্রেতা ধরে রাখতে সর্বাধিক বিক্রিত পণ্যগুলোর পাশে মানসম্মত নতুন পণ্য যোগ করার চেষ্টা করুন।\n"

    # 4. Actionable Advice
    insights += "\n### দোকানদারের জন্য সরাসরি পালনযোগ্য পরামর্শ\n\n"
    insights += f"১. ব্যবসার প্রধান পণ্য হিসেবে '{top_product}' এর সরবরাহ সবসময় সচল রাখুন।\n"
    if low_stock:
        insights += "২. কম স্টকের পণ্যগুলোর তালিকা প্রস্তুত করে আজই ডিলারের কাছে নতুন অর্ডার দিন।\n"
    if dead_stock:
        insights += "৩. অচল পণ্যগুলো দোকানের আকর্ষণীয় জায়গায় প্রদর্শন করুন বা বান্ডেল আকারে বিক্রি করুন।\n"
    insights += "৪. ক্রেতাদের চাহিদা বুঝতে নিয়মিতSQLite লোকাল ডাটাবেজে বেচাকেনার হিসাব লিখে রাখুন।"
    
    return insights


@router.post(
    "/generate-insight",
    response_model=InsightResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Shop Business Insights",
    description=(
        "Processes sales and stock data locally, calculates key retail metrics, "
        "checks in-memory cache to save tokens, and calls Groq with fallback to local rule-engine."
    )
)
async def generate_insight(request: InsightRequest) -> InsightResponse:
    """
    POST /generate-insight
    1. Performs calculations (revenue, top products, low stock, dead stock) locally in Python.
    2. Builds a metrics summary dictionary.
    3. Checks the in-memory TTL cache using the metrics summary to prevent redundant Groq calls.
    4. Invokes Groq using llama-3.1-8b-instant with strict token limits (concise response).
    5. Falls back to llama-3.3-70b-versatile, and finally to local rule-based fallback engine if Groq is blocked.
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

        # 2. Compute total metrics
        total_revenue = sum(item.revenue for item in request.sales)
        total_qty = sum(item.qty for item in request.sales)

        # 3. Identify top selling product by quantity sold
        if product_sales_qty:
            top_product = max(product_sales_qty, key=lambda k: product_sales_qty[k])
        else:
            top_product = "None"

        # 4. Product ranking by revenue (sorting descending)
        sorted_by_revenue = sorted(product_sales_revenue.items(), key=lambda x: x[1], reverse=True)
        top_revenue_list = [{"product": p, "revenue": r} for p, r in sorted_by_revenue[:5]]
        revenue_ranking_str = ", ".join([f"{p} (৳{r:.2f})" for p, r in sorted_by_revenue[:5]])

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
                if product_sales_revenue.get(p, 0.0) == 0.0:
                    dead_stock_products.append(p)

        # 8. Create computed summary representation for caching key
        summary_dict = {
            "total_revenue": total_revenue,
            "total_qty": total_qty,
            "top_product": top_product,
            "top_revenue_list": top_revenue_list,
            "low_stock_products": sorted(low_stock_products),
            "dead_stock_products": sorted(dead_stock_products)
        }

        # 9. Query Cache to see if we have a fresh generated response for this metrics signature
        cached_insight = insight_cache.get(request.shop_name, request.period, summary_dict)
        if cached_insight:
            analytics_summary = AnalyticsSummary(
                total_revenue=total_revenue,
                top_product=top_product,
                low_stock=low_stock_products
            )
            return InsightResponse(
                success=True,
                analytics=analytics_summary,
                ai_insight_bn=cached_insight,
                model="cache-hit"
            )

        # 10. Cache missed. Formulate compact prompts for the Groq call (extremely optimized for rate limit tokens)
        low_stock_str = ", ".join(low_stock_products) if low_stock_products else "None"
        dead_stock_str = ", ".join(dead_stock_products) if dead_stock_products else "None"

        # System instructions are simplified and request ultra-concise responses to minimize completion tokens
        system_instruction = (
            "You are a friendly, expert retail consultant speaking fluent Bengali. "
            "Write a brief, high-value shop insight report in Bengali. "
            "IMPORTANT: Limit the entire response to 120-150 words maximum. Be extremely concise. "
            "Structure into 4 short sections:\n"
            "1. ব্যবসার অবস্থা বিশ্লেষণ (Insights)\n"
            "2. স্টক উন্নত করার পরামর্শ (Stock suggestions)\n"
            "3. ভবিষ্যৎ বিক্রয়ের ট্রেন্ড (Future trends)\n"
            "4. দোকানদারের জন্য পরামর্শ (Actionable advice)"
        )

        user_content = (
            f"দোকান: {request.shop_name}\n"
            f"রাজস্ব: ৳{total_revenue:.0f}\n"
            f"সেরা পণ্য: {top_product}\n"
            f"শীর্ষ পণ্যসমূহ: {revenue_ranking_str}\n"
            f"কম স্টক (<১০): {low_stock_str}\n"
            f"অচল স্টক (বিক্রি ০): {dead_stock_str}\n"
            "এই তথ্যের ভিত্তিতে সংক্ষেপে বাংলায় পরামর্শ দিন।"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        # 11. Call Groq with multiple layers of fallback to avoid rate limits or service denial
        model_name = "llama-3.1-8b-instant"
        ai_insight_text = ""
        
        try:
            # First attempt: llama-3.1-8b-instant (low token usage model)
            ai_insight_text, _ = await groq_service.generate_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=350,  # Strict limit to save token rate limits (TPM)
                model=model_name
            )
        except Exception as api_err:
            logger.warning(f"Primary model {model_name} failed: {api_err}. Trying fallback model '{settings.GROQ_MODEL}'...")
            try:
                # Second attempt: fallback to settings model (e.g. llama-3.3-70b-versatile)
                model_name = settings.GROQ_MODEL
                ai_insight_text, _ = await groq_service.generate_chat_completion(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=350,
                    model=model_name
                )
            except Exception as final_api_err:
                # Third attempt: Local rule-based fallback generator (100% success rate, 0 token usage, zero latency)
                logger.error(f"Fallback model also failed: {final_api_err}. Activating local fallback generator...")
                model_name = "local-rule-engine"
                ai_insight_text = generate_local_fallback_insights(
                    shop_name=request.shop_name,
                    period=request.period,
                    total_revenue=total_revenue,
                    top_product=top_product,
                    low_stock=low_stock_products,
                    dead_stock=dead_stock_products
                )

        # 12. Update Cache with the newly computed insights
        if model_name != "local-rule-engine":
            insight_cache.set(request.shop_name, request.period, summary_dict, ai_insight_text)

        # 13. Construct response
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
