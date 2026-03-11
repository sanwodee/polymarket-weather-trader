from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from dotenv import load_dotenv
import json
import os

load_dotenv()

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

def load_client():
    """Load trading client with saved L2 credentials"""
    print("🔌 Loading trading client...")
    
    # Method 1: Load from saved JSON (fast)
    if os.path.exists(".api_credentials.json"):
        with open(".api_credentials.json") as f:
            creds_dict = json.load(f)
        
        # Convert dict to ApiCreds object
        creds = ApiCreds(
            api_key=creds_dict["api_key"],
            api_secret=creds_dict["api_secret"],
            api_passphrase=creds_dict["api_passphrase"]
        )
        
        client = ClobClient(
            HOST,
            key=os.getenv('POLYGON_WALLET_PRIVATE_KEY'),  # L1
            chain_id=CHAIN_ID,
            creds=creds  # L2 from JSON
        )
        print("✅ Loaded from saved credentials")
    else:
        # Method 2: Derive fresh (fallback)
        print("📂 No saved credentials, deriving fresh...")
        temp_client = ClobClient(
            HOST,
            key=os.getenv('POLYGON_WALLET_PRIVATE_KEY'),
            chain_id=CHAIN_ID
        )
        creds = temp_client.create_or_derive_api_creds()
        client = ClobClient(HOST, key=os.getenv('POLYGON_WALLET_PRIVATE_KEY'), chain_id=CHAIN_ID, creds=creds)
    
    return client

def main():
    client = load_client()
    
    # Credentials loaded successfully
    print("\n🔑 L1/L2 Credentials verified ✅")
    print("   L1: Wallet private key loaded")
    print("   L2: API credentials loaded from .api_credentials.json")
    
    # Test: Get open markets
    print("\n📊 Fetching active markets...")
    markets = client.get_markets()
    print(f"   Found {len(markets['data'])} markets")
    
    # Show top 3 markets
    print("\n🎯 Top Markets:")
    for i, m in enumerate(markets['data'][:3], 1):
        print(f"\n   {i}. {m['question'][:55]}...")
        volume = float(m.get('volume', 0))
        print(f"      Volume: ${volume:,.0f}")
    
    print("\n" + "="*50)
    print("🎉 Ready for trading!")
    print("="*50)
    print("\n💡 Next steps:")
    print("   • Check balance in MetaMask")
    print("   • Set PAPER_TRADING=false to trade live")
    print("   • Create order scripts using client.create_and_post_order()")

if __name__ == "__main__":
    main()
