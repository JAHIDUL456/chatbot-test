import asyncio
import httpx


async def test_generate_insight():
    payload = {
        "shop_name": "Rahman Brothers Grocery",
        "period": "last_30_days",
        "sales": [
            {"product": "Miniket Rice 25kg", "qty": 15, "revenue": 24000},
            {"product": "Soyabean Oil 5L", "qty": 40, "revenue": 36000},
            {"product": "Sugar 1kg", "qty": 100, "revenue": 13000},
            {"product": "Lentil 1kg", "qty": 50, "revenue": 7000},
            {"product": "Mustard Oil 1L", "qty": 0, "revenue": 0}
        ],
        "stock": [
            {"product": "Miniket Rice 25kg", "remaining": 8},   # low stock (< 10)
            {"product": "Soyabean Oil 5L", "remaining": 12},
            {"product": "Sugar 1kg", "remaining": 5},          # low stock (< 10)
            {"product": "Lentil 1kg", "remaining": 22},
            {"product": "Mustard Oil 1L", "remaining": 15},     # remaining > 0, revenue == 0 -> dead stock
            {"product": "Salt 1kg", "remaining": 50}            # remaining > 0, no sales record -> dead stock
        ]
    }

    url = "http://127.0.0.1:8000/generate-insight"
    
    print("Sending request to FastAPI endpoint...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload)
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print("\n--- Analytics Response ---")
                print(f"Success: {data.get('success')}")
                print(f"Model Used: {data.get('model')}")
                print("Analytics Summary:")
                print(f"  Total Revenue: ৳{data.get('analytics', {}).get('total_revenue')}")
                print(f"  Top Selling Product: {data.get('analytics', {}).get('top_product')}")
                print(f"  Low Stock Products: {data.get('analytics', {}).get('low_stock')}")
                print("\n--- AI Bengali Insights ---")
                print(data.get('ai_insight_bn'))
            else:
                print("Error Details:")
                print(response.text)
        except Exception as e:
            print(f"Request failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_generate_insight())
