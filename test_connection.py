from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

print("=" * 50)
print("Polymarket Connection Test")
print("=" * 50)

# Get private key from .env
PRIVATE_KEY = os.getenv('POLYGON_WALLET_PRIVATE_KEY')
PAPER_TRADING = os.getenv('PAPER_TRADING', 'true').lower() == 'true'

if not PRIVATE_KEY:
    print("❌ Error: PRIVATE_KEY not found in .env file")
    exit(1)

print(f"🔑 Private key loaded: {'Yes' if PRIVATE_KEY else 'No'}")
print(f"🧮 Paper trading: {'Yes' if PAPER_TRADING else 'No (LIVE TRADING!)'}")
print()

# Polymarket connection settings
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

print("🌐 Connecting to Polymarket...")
print(f"   Host: {HOST}")
print(f"   Chain ID: {CHAIN_ID}")

try:
    # Step 1: Create temporary client to derive API credentials (L1 → L2)
    print("\n🔐 Deriving L2 API credentials from your wallet...")
    temp_client = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
    
    # This creates the L2 credentials
    api_creds = temp_client.create_or_derive_api_creds()
    
    print("✅ L2 Credentials derived successfully!")
    print(f"\n   📋 API Key: {api_creds.api_key}")
    print(f"   🔒 Secret: {api_creds.api_secret[:20]}... (truncated)")
    print(f"   📝 Passphrase: {api_creds.api_passphrase}")
    
    # Step 2: Initialize full trading client with L1 + L2
    print("\n🔗 Initializing trading client...")
    client = ClobClient(
        HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        creds=api_creds
    )
    
    print("✅ Client initialized successfully!")
    
    # Step 3: Test connection - fetch active markets
    print("\n📊 Testing connection by fetching markets...")
    markets = client.get_markets()  # This actually uses your credentials
    
    print(f"✅ Successfully fetched {len(markets['data'])} markets!")
    print(f"\n🎯 Sample market: {markets['data'][0]['question'] if markets['data'] else 'No markets found'}")
    
    print("\n" + "=" * 50)
    print("🎉 SUCCESS! Your L1/L2 setup is working!")
    print("=" * 50)
    print(f"\n💡 L1 (Wallet): Your private key")
    print(f"💡 L2 (API):  Derived credentials above")
    print(f"\n🧪 Currently in PAPER TRADING mode")
    print(f"   To go live: Set PAPER_TRADING=false in .env")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\n💡 Troubleshooting:")
    print("   - Is your private key valid?")
    print("   - Do you have POL tokens for gas?")
    print("   - Do you have USDC.e in your wallet?")
