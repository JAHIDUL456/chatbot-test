import asyncio
import httpx
import time


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
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Call 1: Expecting a cache miss (calling Groq LLM)
        print("--- [Call 1] Sending request (Cache Miss expected) ---")
        start_time = time.time()
        try:
            response = await client.post(url, json=payload)
            duration = time.time() - start_time
            print(f"Status Code: {response.status_code} | Duration: {duration:.2f}s")
            if response.status_code == 200:
                data = response.json()
                print(f"Success Flag: {data.get('success')}")
                print(f"Engine/Model Used: {data.get('model')}")
                print(f"Top Product: {data.get('analytics', {}).get('top_product')}")
                print("\nInsights Preview:")
                print("\n".join(data.get('ai_insight_bn', '').split('\n')[:5]) + "\n...")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Request failed: {e}")

        print("\n" + "="*50 + "\n")

        # Call 2: Expecting a cache hit (serving immediately from memory)
        print("--- [Call 2] Sending identical request (Cache Hit expected) ---")
        start_time = time.time()
        try:
            response = await client.post(url, json=payload)
            duration = time.time() - start_time
            print(f"Status Code: {response.status_code} | Duration: {duration:.2f}s")
            if response.status_code == 200:
                data = response.json()
                print(f"Success Flag: {data.get('success')}")
                print(f"Engine/Model Used: {data.get('model')} (Zero LLM token usage!)")
                print(f"Top Product: {data.get('analytics', {}).get('top_product')}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Request failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_generate_insight())
