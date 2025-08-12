# import httpx
# import os
# from dotenv import load_dotenv

# load_dotenv()

# API_KEY = os.getenv("FMCSA_API_KEY")
# BASE_URL = "https://mobile.fmcsa.dot.gov/qc/services/carriers/docket-number"

# async def verify_mc_number(mc_number: str):
#     if not mc_number.isdigit():
#         return {"valid": False, "reason": "Invalid MC number format"}

#     url = f"{BASE_URL}/{mc_number}"
#     params = {
#         "webKey": API_KEY
#     }

#     async with httpx.AsyncClient() as client:
#         response = await client.get(url, params=params)

#     if response.status_code != 200:
#         return {"valid": False, "reason": f"FMCSA API error: {response.status_code}"}

#     data = response.json()
#     print(data)
#     if not data.get("content"):
#         return {"valid": False, "reason": "Carrier not found"}

#     carrier_info = data["content"][0].get("carrier", {})

#     return {
#         "valid": True,
#         "mc_number": mc_number,
#         "company_name": carrier_info.get("legalName", "Unknown"),
#         "status": carrier_info.get("carrierOperation", {}).get("carrierOperationDesc", "Unknown")
#     }
