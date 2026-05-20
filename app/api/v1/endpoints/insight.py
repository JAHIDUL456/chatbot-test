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
    period: str,
    total_revenue: float,
    revenue_growth: float,
    inventory_value: float,
    dead_stock_value: float,
    top_product: str,
    stockout_predictions: List[str],
    sales_velocity_alerts: List[str],
    customer_baki: float,
    supplier_baki: float,
    extra_stats: Dict[str, Any]
) -> str:
    """
    Generates a comprehensive, long-form local fallback report covering the entire inventory portfolio.
    """
    growth_direction = "বৃদ্ধি" if revenue_growth >= 0 else "হ্রাস"
    growth_sign = "+" if revenue_growth >= 0 else ""
    net_receivables = customer_baki - supplier_baki
    net_status = "সারপ্লাস (ইতিবাচক)" if net_receivables >= 0 else "ঘাটতি (নেতিবাচক)"
    
    velocity_tiers = extra_stats.get("velocity_tiers", {})
    dead_details = extra_stats.get("dead_details", [])
    overstock = extra_stats.get("overstock", [])
    revenue_concentration = extra_stats.get("revenue_concentration", "")
    declining_trends = extra_stats.get("declining_trends", [])
    accelerating_trends = extra_stats.get("accelerating_trends", [])
    
    insights = (
        f"### ১. ব্যবসার সামগ্রিক অবস্থা ও বিক্রয় প্রক্ষেপণ (Sales & Revenue Projections)\n\n"
        f"*   **রাজস্ব ও প্রবৃদ্ধি:** গত {period}-এ **{shop_name}**-এর মোট বিক্রয়লব্ধ রাজস্ব **৳{total_revenue:,.2f}**। "
        f"আগের মেয়াদের তুলনায় বিক্রি **{growth_sign}{revenue_growth:.1f}% {growth_direction}** পেয়েছে। এই ধারাবাহিকতা বজায় থাকলে পরবর্তী মাসে সম্ভাব্য বিক্রয় লক্ষ্যমাত্রা **৳{total_revenue * (1 + revenue_growth/100):,.2f}**।\n"
        f"*   **রাজস্বের কেন্দ্রীকরণ (80/20 Rule):** {revenue_concentration}\n"
        f"*   **বিক্রয় বেগ প্রোফাইল:** বর্তমানে দোকানে মোট **{velocity_tiers.get('fast', 0)}** টি পণ্য দ্রুত গতিতে (Fast-moving), **{velocity_tiers.get('steady', 0)}** টি পণ্য মাঝারি গতিতে (Steady-moving) এবং **{velocity_tiers.get('slow', 0)}** টি পণ্য ধীর গতিতে বিক্রি হচ্ছে।\n"
    )

    if declining_trends or accelerating_trends:
        insights += "\n### ২. সাম্প্রতিক ট্রেন্ড ও চাহিদা পরিবর্তন (Demand Trajectory Alerts)\n\n"
        if declining_trends:
            insights += "*   **📉 চাহিদা হ্রাস পাওয়া পণ্য (ঝুঁকিপূর্ণ):**\n"
            for alert in declining_trends[:3]:
                insights += f"    *   {alert}\n"
            insights += "    *   *পরামর্শ:* এই পণ্যগুলোর চাহিদা সাম্প্রতিক সময়ে ব্যাপক কমে গেছে। এগুলো নতুন করে স্টক করবেন না। বর্তমান স্টক দ্রুত খালি করুন।\n"
        if accelerating_trends:
            insights += "*   **📈 চাহিদা বৃদ্ধি পাওয়া পণ্য (লাভজনক):**\n"
            for alert in accelerating_trends[:3]:
                insights += f"    *   {alert}\n"
            insights += "    *   *পরামর্শ:* এই পণ্যগুলোর বিক্রি দ্রুত বাড়ছে। স্টকআউট এড়াতে বেশি করে স্টক নিয়ে রাখুন।\n"

    insights += (
        f"\n### ৩. সরবরাহ চেইন ও স্টকআউট পূর্বাভাস (Stockout & Supply Chain Projections)\n\n"
    )
    if stockout_predictions:
        insights += "*   **স্টক ফুরিয়ে যাওয়ার ঝুঁকিতে থাকা পণ্য (১-৭ দিন বাকি):**\n"
        for alert in stockout_predictions[:5]:
            insights += f"    *   ⚠️ **{alert}**\n"
        insights += "    *   **ঝুঁকি বিশ্লেষণ:** এই পণ্যগুলো ফুরিয়ে গেলে আপনার দৈনিক রাজস্ব প্রবাহ ব্যাহত হবে। জরুরি ভিত্তিতে পুনরায় অর্ডার করতে হবে।\n"
    else:
        insights += "*   **স্টক সতর্কতা:** বর্তমানে কোনো পণ্যেরই অতি-জরুরি স্টকআউটের ঝুঁকি নেই।\n"

    insights += (
        f"\n### ৪. মূলধন অবরুদ্ধ ও বকেয়া নগদ প্রবাহ (Locked Capital & Dues Resolution)\n\n"
        f"*   **বকেয়া নগদ ব্যালেন্স:** কাস্টমারদের কাছে বকেয়া পাওনা **৳{customer_baki:,.2f}** এবং মহাজনদের কাছে আপনার দেনা **৳{supplier_baki:,.2f}**। "
        f"আপনার নেট বকেয়া অবস্থান হচ্ছে **৳{net_receivables:,.2f}** ({net_status})।\n"
        f"*   **অচল মূলধন (Dead Capital):** দোকানে বর্তমানে **৳{dead_stock_value:,.2f}** মূল্যের মালামাল সম্পূর্ণ অচল হয়ে পড়ে আছে (বিক্রি শূন্য)।\n"
    )
    if dead_details:
        insights += "    *   **শীর্ষ অচল পণ্যের তালিকা (মূলধন আটকে আছে):**\n"
        for name, val in dead_details[:3]:
            insights += f"        *   ❌ **{name}** (আটকে আছে ৳{val:,.2f})\n"

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

        logger.info(f"Generating comprehensive AI Agent insights for '{shop_name}' over period '{period}'")

        sales_list = request.sales or []
        stock_list = request.stock or []

        # 1. Split timeline into Month 1 (0-30 days), Month 2 (31-60 days), and Month 3 (61-90 days)
        now = datetime.utcnow()
        m1_start = now - timedelta(days=30)
        m2_start = now - timedelta(days=60)
        m3_start = now - timedelta(days=90)

        # Sales filter for the specific active duration (requested period: 7 or 30 days)
        days_limit = 7 if period == "last_7_days" else 30
        active_start_date = now - timedelta(days=days_limit)

        # 2. Aggregating sales by time buckets for trajectory tracking
        sales_m1: Dict[str, float] = {}
        sales_m2: Dict[str, float] = {}
        sales_m3: Dict[str, float] = {}
        
        # Current active period revenue mapping
        product_sales_revenue = {}
        product_sales_qty = {}

        for item in sales_list:
            p = (item.product or "Unknown").strip()
            qty = item.qty if item.qty is not None else 0.0
            rev = item.revenue if item.revenue is not None else 0.0
            date_val = parse_date_naive(item.date)

            # Sum up in monthly buckets
            if date_val >= m1_start:
                sales_m1[p] = sales_m1.get(p, 0.0) + qty
            elif date_val >= m2_start:
                sales_m2[p] = sales_m2.get(p, 0.0) + qty
            elif date_val >= m3_start:
                sales_m3[p] = sales_m3.get(p, 0.0) + qty

            # Sum up for selected active period
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

        # 4. Top selling product detection for current active period
        top_product = max(product_sales_qty, key=lambda k: product_sales_qty[k]) if product_sales_qty else "None"

        # 5. Top revenue product list (current active period)
        sorted_by_revenue = sorted(product_sales_revenue.items(), key=lambda x: x[1], reverse=True)
        revenue_ranking_str = ", ".join([f"{p} (৳{r:.2f})" for p, r in sorted_by_revenue[:8]])

        # 6. Revenue Concentration calculation (80/20 rule)
        revenue_concentration_msg = ""
        if total_revenue > 0:
            running_rev = 0.0
            top_contributors = 0
            for p, rev in sorted_by_revenue:
                running_rev += rev
                top_contributors += 1
                if running_rev >= total_revenue * 0.8:
                    break
            percentage_contrib = (top_contributors / len(product_sales_revenue)) * 100 if product_sales_revenue else 0
            revenue_concentration_msg = f"আপনার মোট রাজস্বের ৮০% অর্জিত হচ্ছে শীর্ষ {top_contributors}টি পণ্য ({percentage_contrib:.1f}%) থেকে। বাকি মালামাল অলস মূলধন ধরে রেখেছে।"
        else:
            revenue_concentration_msg = "তথ্য কম থাকার কারণে রাজস্ব ঘনীভবন পরিমাপ করা যায়নি।"

        # 7. Inventory value and Dead Capital calculations
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
            
            # Dead Stock: Active stock remaining, but 0 sales generated in the active period
            if product_sales_revenue.get(p, 0.0) == 0.0 and cost > 0:
                dead_stock_value += cost
                dead_stock_details.append((p, cost))

        dead_stock_details = sorted(dead_stock_details, key=lambda x: x[1], reverse=True)

        # 8. Time-series Trajectory logic (declining vs accelerating trends)
        declining_trends = []
        accelerating_trends = []
        all_unique_products = set(sales_m1.keys()) | set(sales_m2.keys()) | set(sales_m3.keys())

        for p in all_unique_products:
            m1_qty = sales_m1.get(p, 0.0)
            m2_qty = sales_m2.get(p, 0.0)
            m3_qty = sales_m3.get(p, 0.0)

            # Case: Declining trend (Month 3 > Month 2 > Month 1 or sharp drop)
            if m3_qty > 0 and m1_qty < (m2_qty * 0.7) and m2_qty < (m3_qty * 1.2):
                # Dropped by more than 30% from month 2
                declining_trends.append(f"**{p}** (বিক্রি কমেছে: ৩ মাস আগে {m3_qty:.0f}টি ➡️ গত মাসে {m2_qty:.0f}টি ➡️ এই মাসে {m1_qty:.0f}টি)")
            # Case: Accelerating trend (Month 1 > Month 2 by 40%+)
            elif m1_qty > (m2_qty * 1.4) and (m1_qty > 3 or m2_qty > 3):
                accelerating_trends.append(f"**{p}** (বিক্রি বেড়েছে: গত মাসে {m2_qty:.0f}টি ➡️ এই মাসে {m1_qty:.0f}টি)")

        # 9. Sales velocity and Stockout/Overstock prediction
        stockout_predictions = []
        sales_velocity_alerts = []
        overstock_alerts = []
        
        velocity_tiers = {"fast": 0, "steady": 0, "slow": 0}
        span_days = max(days_limit, 1)

        for p, qty in product_sales_qty.items():
            daily_velocity = qty / span_days
            
            # Tiering
            if daily_velocity >= 1.0:
                velocity_tiers["fast"] += 1
            elif daily_velocity >= 0.3:
                velocity_tiers["steady"] += 1
            else:
                velocity_tiers["slow"] += 1

            if daily_velocity > 0.3:
                sales_velocity_alerts.append(f"{p} ({daily_velocity:.1f}টি/দিন)")
            
            # Predict stockout duration
            remaining_stock = product_stock_levels.get(p, 0.0)
            if daily_velocity > 0:
                days_left = remaining_stock / daily_velocity
                if days_left <= 7:
                    stockout_predictions.append(f"{p} ({days_left:.1f} দিন বাকি)")
                elif days_left > 45:
                    overstock_alerts.append(f"{p} ({days_left:.0f} দিনের স্টক বাকি)")

        # Prepare extra analytical context
        extra_stats = {
            "velocity_tiers": velocity_tiers,
            "dead_details": dead_stock_details,
            "overstock": overstock_alerts,
            "revenue_concentration": revenue_concentration_msg,
            "declining_trends": declining_trends,
            "accelerating_trends": accelerating_trends
        }

        # 10. Create computed summary representation for caching key
        summary_dict = {
            "total_revenue": total_revenue,
            "revenue_growth": round(revenue_growth, 2),
            "inventory_value": inventory_value,
            "dead_stock_value": dead_stock_value,
            "top_product": top_product,
            "stockout_predictions": sorted(stockout_predictions),
            "sales_velocity_alerts": sorted(sales_velocity_alerts),
            "customer_baki": customer_baki,
            "supplier_baki": supplier_baki,
            "declining_trends_hash": str(sorted(declining_trends)),
            "accelerating_trends_hash": str(sorted(accelerating_trends))
        }

        # 11. Query Cache
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

        # 12. Invoke Groq AI with trajectory & recency prompts
        system_instruction = (
            "You are an elite, highly strategic AI Retail Business Strategist & Inventory Agent. "
            "Your goal is to analyze the complete, aggregated store portfolio data, historical monthly trends, and cash flow levels, "
            "and write an extremely detailed, highly accurate, long-form strategic business blueprint in professional Bengali. "
            "Do not focus on only one top product; address the health of the entire inventory portfolio to maximize real profits.\n\n"
            "Format the output strictly into these 4 sections using clear markdown headings:\n"
            "১. ব্যবসার সামগ্রিক অবস্থা ও বিক্রয় প্রক্ষেপণ (Sales & Revenue Projections)\n"
            "২. সাম্প্রতিক ট্রেন্ড ও চাহিদা পরিবর্তন (Demand Trajectory Alerts)\n"
            "৩. সরবরাহ চেইন ও স্টকআউট পূর্বাভাস (Stockout & Supply Chain Projections)\n"
            "৪. মূলধন অবরুদ্ধ ও লোকসান এড়ানোর অ্যাকশন প্ল্যান (Locked Capital & Profit Actions)\n\n"
            "Core Guidelines:\n"
            "- Speak directly to the merchant with authority. Use bold values, currency figures (৳), and growth percentages.\n"
            "- In Section 2, focus deeply on Time-Decay demand trajectory. Call out products that are declining in sales (was popular 2-3 months ago but dropped this month) and warn the merchant not to restock them. Contrast this with accelerating demand items.\n"
            "- Contrast customer receivables vs. supplier payables, advising on collection strategies to resolve supplier debt.\n"
            "- Propose realistic promotion bundles matching top-velocity products with dead stock items to recover locked capital.\n"
            "- Keep the response comprehensive, deeply analytical, and useful. Avoid generic filler. Limit to 380-480 words."
        )

        dead_stock_list_str = ", ".join([f"{name} (৳{val:.2f})" for name, val in dead_stock_details[:5]]) if dead_stock_details else "নেই"
        declining_list_str = "; ".join(declining_trends[:4]) if declining_trends else "কোনো উল্লেখযোগ্য অবনতি নেই"
        accelerating_list_str = "; ".join(accelerating_trends[:4]) if accelerating_trends else "কোনো উল্লেখযোগ্য বৃদ্ধি নেই"
        overstock_list_str = ", ".join(overstock_alerts[:5]) if overstock_alerts else "নেই"

        user_content = (
            f"দোকানের নাম: {shop_name}\n"
            f"বিশ্লেষণ সময়কাল: {period}\n"
            f"মোট রাজস্ব: ৳{total_revenue:.2f}\n"
            f"রাজস্ব প্রবৃদ্ধি হার: {revenue_growth:.1f}%\n"
            f"মোট ইনভেন্টরি মূলধন (স্টকে থাকা পণ্যের ক্রয়মূল্য): ৳{inventory_value:.2f}\n"
            f"মোট অচল পণ্যে আটকে থাকা অকেজো মূলধন: ৳{dead_stock_value:.2f}\n"
            f"শীর্ষ অচল পণ্যের তালিকা ও মূলধন: {dead_stock_list_str}\n"
            f"ক্রেতাদের কাছে মোট বকেয়া পাওনা (কাস্টমার বাকি): ৳{customer_baki:.2f}\n"
            f"মহাজনদের কাছে মোট বকেয়া দেনা (সাপ্লায়ার বাকি): ৳{supplier_baki:.2f}\n"
            f"মোট রাজস্বের কেন্দ্রীকরণ (৮০/২০ সূত্র): {revenue_concentration_msg}\n"
            f"বিক্রয়ের গতিবেগ প্রোফাইল: {velocity_tiers.get('fast', 0)}টি দ্রুত বিক্রেতা, {velocity_tiers.get('steady', 0)}টি মাঝারি বিক্রেতা, {velocity_tiers.get('slow', 0)}টি ধীর বিক্রেতা\n"
            f"সর্বাধিক বিক্রিত পণ্য: {top_product}\n"
            f"শীর্ষ ৮ পণ্য রাজস্ব: {revenue_ranking_str}\n"
            f"স্টকআউট পূর্বাভাস (দিন বাকি): {', '.join(stockout_predictions) if stockout_predictions else 'নেই'}\n"
            f"অতিরিক্ত ওভারস্টক পণ্য তালিকা (প্রয়োজনের চেয়ে বেশি স্টক): {overstock_list_str}\n"
            f"📉 চাহিদা হ্রাস পাওয়া পণ্যের ট্রাজেক্টরি (Month 3 ➡️ Month 2 ➡️ Month 1): {declining_list_str}\n"
            f"📈 চাহিদা বৃদ্ধি পাওয়া পণ্যের ট্রাজেক্টরি: {accelerating_list_str}\n\n"
            "এই বিস্তারিত ডিস্ট্রিবিউশন তথ্যের ওপর ভিত্তি করে দোকানটিকে একটি বড় লাভজনক ডেসিনেশনে পরিণত করার জন্য একটি শক্তিশালী অ্যাকশন প্ল্যান ও রিয়ালিস্টিক প্রজেকশন দিন।"
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
                temperature=0.75,
                max_tokens=1100,
                model=model_name
            )
        except Exception as api_err:
            logger.warning(f"Primary model {model_name} failed: {api_err}. Trying fallback...")
            try:
                model_name = settings.GROQ_MODEL
                ai_insight_text, _ = await groq_service.generate_chat_completion(
                    messages=messages,
                    temperature=0.75,
                    max_tokens=1100,
                    model=model_name
                )
            except Exception as final_api_err:
                logger.error(f"Fallback failed: {final_api_err}. Activating local engine...")
                model_name = "local-rule-engine"
                ai_insight_text = generate_local_fallback_insights(
                    shop_name=shop_name,
                    period=period,
                    total_revenue=total_revenue,
                    revenue_growth=revenue_growth,
                    inventory_value=inventory_value,
                    dead_stock_value=dead_stock_value,
                    top_product=top_product,
                    stockout_predictions=stockout_predictions,
                    sales_velocity_alerts=sales_velocity_alerts,
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
