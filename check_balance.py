import json
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()

def check_balance():
    """Check wallet USDC balance and POL gas"""
    HOST = "https://clob.polymarket.com"
    CHAIN_ID = 137
    
    # Load credentials
    with open(".api_credentials.json") as f:
        creds_dict = json.load(f)
    
    creds = ApiCreds(
        api_key=creds_dict["api_key"],
        api_secret=creds_dict["api_secret"],
        api_passphrase=creds_dict["api_passphrase"]
    )
    
    client = ClobClient(
        HOST,
        key=os.getenv('POLYGON_WALLET_PRIVATE_KEY'),
        chain_id=CHAIN_ID,
        creds=creds
    )
    
    # Get API key info (shows your address)
    # Note: py-clob-client doesn't have direct balance check
    # You need web3 for on-chain balance
    
    print("=" * 50)
    print("💰 Balance Check")
    print("=" * 50)
    print("\n⚠️  Note: Python SDK doesn't have direct balance method.")
    print("   Check your balance in MetaMask manually.")
    print("\n📍 Your wallet address:")
    # Address derived from private key is your funder
    import web3
    w3 = web3.Web3()
    account = w3.eth.account.from_key(os.getenv('POLYGON_WALLET_PRIVATE_KEY'))
    print(f"   {account.address}")
    print("\n🔍 Check this address on:")
    print(f"   https://polygonscan.com/address/{account.address}")
    print("\n💡 What to look for:")
    print("   • USDC.e token balance (for trading)")
    print("   • POL balance (for gas fees, need ~0.1-1 POL)")

if __name__ == "__main__":
    try:
        check_balance()
    except ImportError:
        print("⚠️  Need web3 library. Run: pip install web3")
        print("\n📍 Your wallet address can also be found in MetaMask")
        print("   - Switch to Polygon network")
        print("   - Copy your wallet address")
        print("   - Check on polygonscan.com")
