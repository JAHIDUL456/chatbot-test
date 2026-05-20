import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.insight import InsightRequest, InsightResponse, AnalyticsSummary
from app.services.groq_client import groq_service
from app.services.insight_cache import insight_cache

logger = logging.getLogger(__name__)
router = APIRouter()


def parse_date_naive(date_str: Optional[str]) -> datetime:
    """Parses date string safely to a naive datetime."""
    if not date_str:
        return datetime.utcnow()
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def generate_local_fallback_insights(
    shop_name: str,
    total_revenue: float,
    revenue_growth: float,
    dead_stock_value: float,
    top_product: str,
    stockout_predictions: List[str],
    customer_baki: float,
    supplier_baki: float,
    extra_stats: Dict[str, Any]
) -> str:
    """
    Generates a simple, direct fallback report with exactly two sections and expanded points.
    """
    growth_sign = "+" if revenue_growth >= 0 else ""
    declining_trends = extra_stats.get("declining_trends", [])
    accelerating_trends = extra_stats.get("accelerating_trends", [])
    
    insights = (
        f"১. লাভ বাড়ানোর নিশ্চিত উপায়:\n"
        f"*   **বেচাকেনা ও প্রবৃদ্ধি:** গত মেয়াদে আপনার মোট বিক্রি হয়েছে **৳{total_revenue:,.2f}** (প্রবৃদ্ধি: **{growth_sign}{revenue_growth:.1f}%**)। পরবর্তী মাসে বিক্রি আরও বাড়াতে আপনার সবচেয়ে বেশি চলা পণ্য **'{top_product}'**-এর স্টক সবসময় ঠিক রাখুন।\n"
    )
    if accelerating_trends:
        insights += f"*   **চাহিদা বাড়ছে:** {accelerating_trends[0]} পণ্যের বিক্রি বাড়ছে। এর স্টক বাড়ালে লাভ বেশি হবে।\n"
    
    insights += (
        f"*   **বকেয়া টাকা তুলুন:** কাস্টমারদের কাছে আপনার পাওনা বাকি **৳{customer_baki:,.2f}**। এই বকেয়া টাকা তুলে ব্যবসায় খাটালে আপনার লাভ বাড়বে।\n"
        f"*   **অচল পণ্য কম্বো প্যাক:** দোকানে **৳{dead_stock_value:,.2f}** টাকার মালামাল অচল পড়ে আছে। এগুলো সর্বাধিক বিক্রিত পণ্যের সাথে প্যাকেজ করে কম দামে বিক্রি করে দিন।\n\n"
    )

    insights += (
        f"২. লোকসান এড়ানোর সতর্কতা:\n"
    )
    if declining_trends:
        insights += f"*   **বিক্রি কমে যাওয়া পণ্য:** {declining_trends[0]}। এই পণ্যগুলোর চাহিদা দিন দিন কমছে। তাই এগুলো আর নতুন করে কিনবেন না, নতুবা লোকসান হবে।\n"
    
    if stockout_predictions:
        insights += f"*   **স্টক শেষ হওয়ার ঝুঁকি:** {', '.join(stockout_predictions[:3])} খুব দ্রুত ফুরিয়ে যাচ্ছে। এগুলো ফুরিয়ে গেলে কাস্টমার ফিরে যাবে এবং বিক্রি হাতছাড়া হবে।\n"
        
    insights += (
        f"*   **মহাজনের দেনা পরিশোধ:** মহাজনের বকেয়া দেনা **৳{supplier_baki:,.2f}** দ্রুত পরিশোধ না করলে মালামাল পাওয়া বন্ধ হয়ে যেতে পারে, যা বড় লোকসানের কারণ হবে।"
    )
    return insights


@router.post(
    "/generate-insight",
    response_model=InsightResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Shop Business Insights",
    description="Processes advanced transaction trends locally and invokes AI for predictive retail insights."
)
async def generate_insight(request: InsightRequest) -> InsightResponse:
    try:
        shop_name = (request.shop_name or "আমার জেনারেল স্টোর").strip()
        period = (request.period or "last_30_days").strip()
        customer_baki = request.customer_baki or 0.0
        supplier_baki = request.supplier_baki or 0.0

        logger.info(f"Generating simplified AI insights for '{shop_name}' over period '{period}'")

        sales_list = request.sales or []
        stock_list = request.stock or []

        # 1. Split timeline into Month 1, Month 2, and Month 3
        now = datetime.utcnow()
        m1_start = now - timedelta(days=30)
        m2_start = now - timedelta(days=60)
        m3_start = now - timedelta(days=90)

        # Sales filter for the specific active duration (requested period: 7 or 30 days)
        days_limit = 7 if period == "last_7_days" else 30
        active_start_date = now - timedelta(days=days_limit)

        # 2. Aggregating sales by time buckets
        sales_m1: Dict[str, float] = {}
        sales_m2: Dict[str, float] = {}
        sales_m3: Dict[str, float] = {}
        
        product_sales_revenue = {}
        product_sales_qty = {}

        for item in sales_list:
            p = (item.product or "Unknown").strip()
            qty = item.qty if item.qty is not None else 0.0
            rev = item.revenue if item.revenue is not None else 0.0
            date_val = parse_date_naive(item.date)

            if date_val >= m1_start:
                sales_m1[p] = sales_m1.get(p, 0.0) + qty
            elif date_val >= m2_start:
                sales_m2[p] = sales_m2.get(p, 0.0) + qty
            elif date_val >= m3_start:
                sales_m3[p] = sales_m3.get(p, 0.0) + qty

            if date_val >= active_start_date:
                product_sales_revenue[p] = product_sales_revenue.get(p, 0.0) + rev
                product_sales_qty[p] = product_sales_qty.get(p, 0.0) + qty

        total_revenue = sum(
            (item.revenue if item.revenue is not None else 0.0) 
            for item in sales_list 
            if parse_date_naive(item.date) >= active_start_date
        )

        # 3. Growth rate calculation (H1 vs H2 of active period)
        midpoint = active_start_date + (now - active_start_date) / 2
        revenue_h1 = 0.0
        revenue_h2 = 0.0
        
        for item in sales_list:
            item_date = parse_date_naive(item.date)
            rev = item.revenue if item.revenue is not None else 0.0
            if active_start_date <= item_date < midpoint:
                revenue_h1 += rev
            elif item_date >= midpoint:
                revenue_h2 += rev
                
        if revenue_h1 > 0:
            revenue_growth = ((revenue_h2 - revenue_h1) / revenue_h1) * 100
        else:
            revenue_growth = 0.0

        # 4. Top selling product detection
        top_product = max(product_sales_qty, key=lambda k: product_sales_qty[k]) if product_sales_qty else "None"

        # 5. Top revenue product list
        sorted_by_revenue = sorted(product_sales_revenue.items(), key=lambda x: x[1], reverse=True)
        revenue_ranking_str = ", ".join([f"{p} (৳{r:.2f})" for p, r in sorted_by_revenue[:5]])

        # 6. Inventory value and Dead Capital calculations
        inventory_value = 0.0
        dead_stock_value = 0.0
        product_stock_levels = {}
        dead_stock_details = []
        
        for item in stock_list:
            p = (item.product or "Unknown").strip()
            rem = item.remaining if item.remaining is not None else 0.0
            buy_price = item.buy_price if item.buy_price is not None else 0.0
            
            product_stock_levels[p] = product_stock_levels.get(p, 0.0) + rem
            cost = rem * buy_price
            inventory_value += cost
            
            if product_sales_revenue.get(p, 0.0) == 0.0 and cost > 0:
                dead_stock_value += cost
                dead_stock_details.append((p, cost))

        dead_stock_details = sorted(dead_stock_details, key=lambda x: x[1], reverse=True)

        # 7. Time-series Trajectory logic
        declining_trends = []
        accelerating_trends = []
        all_unique_products = set(sales_m1.keys()) | set(sales_m2.keys()) | set(sales_m3.keys())

        for p in all_unique_products:
            m1_qty = sales_m1.get(p, 0.0)
            m2_qty = sales_m2.get(p, 0.0)
            m3_qty = sales_m3.get(p, 0.0)

            if m3_qty > 0 and m1_qty < (m2_qty * 0.7) and m2_qty < (m3_qty * 1.2):
                declining_trends.append(f"**{p}** (বিক্রি ৩ মাস আগে ছিল {m3_qty:.0f}টি, এখন মাত্র {m1_qty:.0f}টি)")
            elif m1_qty > (m2_qty * 1.4) and (m1_qty > 3 or m2_qty > 3):
                accelerating_trends.append(f"**{p}** (বিক্রি গত মাসের চেয়ে {m1_qty - m2_qty:.0f}টি বেড়েছে)")

        # 8. Sales velocity and Stockout prediction
        stockout_predictions = []
        sales_velocity_alerts = []
        
        span_days = max(days_limit, 1)
        for p, qty in product_sales_qty.items():
            daily_velocity = qty / span_days
            if daily_velocity > 0.3:
                sales_velocity_alerts.append(f"{p} ({daily_velocity:.1f}টি/দিন)")
            
            remaining_stock = product_stock_levels.get(p, 0.0)
            if daily_velocity > 0:
                days_left = remaining_stock / daily_velocity
                if days_left <= 7:
                    stockout_predictions.append(f"{p} ({days_left:.1f} দিনে ফুরিয়ে যাবে)")

        extra_stats = {
            "declining_trends": declining_trends,
            "accelerating_trends": accelerating_trends
        }

        # 9. Create computed summary representation for caching key
        summary_dict = {
            "total_revenue": total_revenue,
            "revenue_growth": round(revenue_growth, 2),
            "inventory_value": inventory_value,
            "dead_stock_value": dead_stock_value,
            "top_product": top_product,
            "stockout_predictions": sorted(stockout_predictions),
            "customer_baki": customer_baki,
            "supplier_baki": supplier_baki,
            "declining_trends_hash": str(sorted(declining_trends)),
            "accelerating_trends_hash": str(sorted(accelerating_trends))
        }

        # 10. Query Cache
        cached_insight = insight_cache.get(shop_name, period, summary_dict)
        if cached_insight:
            analytics_summary = AnalyticsSummary(
                total_revenue=total_revenue,
                inventory_value=inventory_value,
                dead_stock_value=dead_stock_value,
                revenue_growth=revenue_growth,
                top_product=top_product,
                stockout_predictions=stockout_predictions,
                sales_velocity_alerts=sales_velocity_alerts,
                customer_baki=customer_baki,
                supplier_baki=supplier_baki
            )
            return InsightResponse(
                success=True,
                analytics=analytics_summary,
                ai_insight_bn=cached_insight,
                model="cache-hit"
            )

        # 11. Invoke Groq AI with 2 clear sections - expanded to give even more life-saving profit advice
        system_instruction = (
            "You are a legendary AI Retail Strategy Strategist who writes simple, direct business reports in Bengali "
            "that even a 10-year-old child (class 5 pass student) can instantly understand and act upon to save their business.\n\n"
            "Format the output strictly into these 2 sections using clear markdown headings:\n"
            "১. লাভ বাড়ানোর নিশ্চিত উপায় (Steps for More Profit)\n"
            "২. লোকসান এড়ানোর সতর্কতা (Avoid Loss Warnings)\n\n"
            "Core Guidelines:\n"
            "- Speak directly to the merchant in very simple, friendly, and authoritative Bengali.\n"
            "- Under Section 1, provide 4 highly actionable, clear bullet points: which specific high-growth/popular items to stock up on immediately, how to collect customer baki step-by-step, a dynamic combo bundling idea using dead stock, and a seasonal stocking advice based on history.\n"
            "- Under Section 2, provide 4 extremely direct warnings: which items are crashing in demand and MUST NOT be restocked, which items will run dry this week (stockout predictions), a critical warning on supplier dues to avoid supply suspension, and a warning on dead capital pricing strategy.\n"
            "- Keep sentences short, simple, and punchy. Make it feel extremely premium, expert, and life-saving. Limit to 300-380 words."
        )

        dead_stock_list_str = ", ".join([f"{name} (৳{val:.2f})" for name, val in dead_stock_details[:3]]) if dead_stock_details else "নেই"
        declining_list_str = "; ".join(declining_trends[:3]) if declining_trends else "কোনো উল্লেখযোগ্য অবনতি নেই"
        accelerating_list_str = "; ".join(accelerating_trends[:3]) if accelerating_trends else "কোনো উল্লেখযোগ্য বৃদ্ধি নেই"

        user_content = (
            f"দোকানের নাম: {shop_name}\n"
            f"মোট রাজস্ব: ৳{total_revenue:.2f}\n"
            f"রাজস্ব প্রবৃদ্ধি হার: {revenue_growth:.1f}%\n"
            f"অচল পণ্যে আটকে থাকা অকেজো মূলধন: ৳{dead_stock_value:.2f} (শীর্ষ অচল: {dead_stock_list_str})\n"
            f"কাস্টমারদের কাছে বাকি পাওনা: ৳{customer_baki:.2f}\n"
            f"মহাজনদের কাছে দেনা: ৳{supplier_baki:.2f}\n"
            f"সর্বাধিক বিক্রিত পণ্য: {top_product}\n"
            f"স্টকআউট পূর্বাভাস (দ্রুত শেষ হবে): {', '.join(stockout_predictions) if stockout_predictions else 'নেই'}\n"
            f"📉 বিক্রি কমে যাওয়া পণ্যের তালিকা: {declining_list_str}\n"
            f"📈 বিক্রি বৃদ্ধি পাওয়া পণ্যের তালিকা: {accelerating_list_str}\n\n"
            "উপরে দেওয়া ডেটার ওপর ভিত্তি করে লাভ বাড়ানোর উপায় এবং লোকসান এড়ানোর সতর্কতা খুব সহজে লিখুন।"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        model_name = "llama-3.1-8b-instant"
        ai_insight_text = ""
        
        try:
            ai_insight_text, _ = await groq_service.generate_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=850,
                model=model_name
            )
        except Exception as api_err:
            logger.warning(f"Primary model {model_name} failed: {api_err}. Trying fallback...")
            try:
                model_name = settings.GROQ_MODEL
                ai_insight_text, _ = await groq_service.generate_chat_completion(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=850,
                    model=model_name
                )
            except Exception as final_api_err:
                logger.error(f"Fallback failed: {final_api_err}. Activating local engine...")
                model_name = "local-rule-engine"
                ai_insight_text = generate_local_fallback_insights(
                    shop_name=shop_name,
                    total_revenue=total_revenue,
                    revenue_growth=revenue_growth,
                    dead_stock_value=dead_stock_value,
                    top_product=top_product,
                    stockout_predictions=stockout_predictions,
                    customer_baki=customer_baki,
                    supplier_baki=supplier_baki,
                    extra_stats=extra_stats
                )

        if model_name != "local-rule-engine":
            insight_cache.set(shop_name, period, summary_dict, ai_insight_text)

        analytics_summary = AnalyticsSummary(
            total_revenue=total_revenue,
            inventory_value=inventory_value,
            dead_stock_value=dead_stock_value,
            revenue_growth=revenue_growth,
            top_product=top_product,
            stockout_predictions=stockout_predictions,
            sales_velocity_alerts=sales_velocity_alerts,
            customer_baki=customer_baki,
            supplier_baki=supplier_baki
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
