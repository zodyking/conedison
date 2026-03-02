#!/usr/bin/env python3
"""
Test script for opower library with Con Edison.

This script tests the opower library to fetch real-time meter data
from Con Edison's Opower API.

Usage:
    python test_opower.py --email YOUR_EMAIL --password YOUR_PASSWORD --totp-secret YOUR_TOTP_SECRET

Or set environment variables:
    CONED_EMAIL=your@email.com
    CONED_PASSWORD=yourpassword
    CONED_TOTP_SECRET=yourbase32secret
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

# Add parent path for local testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_opower(email: str, password: str, totp_secret: str):
    """Test opower library with Con Edison credentials."""
    
    try:
        import aiohttp
        from opower import Opower, AggregateType
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Install with: pip install opower")
        return

    print("=" * 60)
    print("OPOWER LIBRARY TEST - Con Edison")
    print("=" * 60)
    print(f"Email: {email}")
    print(f"TOTP Secret: {'*' * (len(totp_secret) - 4)}{totp_secret[-4:]}" if totp_secret else "Not provided")
    print()

    async with aiohttp.ClientSession() as session:
        # Initialize opower with ConEd utility (pass utility name as string)
        opower_client = Opower(
            session=session,
            utility="coned",
            username=email,
            password=password,
            optional_totp_secret=totp_secret if totp_secret else None,
        )

        # Step 1: Login
        print("[1] Logging in to Con Edison...")
        try:
            await opower_client.async_login()
            print("    ✓ Login successful!")
        except Exception as e:
            print(f"    ✗ Login failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # Step 2: Get accounts
        print("\n[2] Fetching accounts...")
        try:
            accounts = await opower_client.async_get_accounts()
            print(f"    ✓ Found {len(accounts)} account(s)")
            
            for i, account in enumerate(accounts):
                print(f"\n    Account {i + 1}:")
                print(f"      UUID: {account.uuid}")
                print(f"      Utility Account ID: {account.utility_account_id}")
                print(f"      Meter Type: {account.meter_type}")
                print(f"      Read Resolution: {account.read_resolution}")
                print(f"      Customer UUID: {account.customer.uuid}")
        except Exception as e:
            print(f"    ✗ Failed to get accounts: {e}")
            return

        if not accounts:
            print("    No accounts found!")
            return

        account = accounts[0]
        print(f"\n    Using first account: {account.utility_account_id}")

        # Step 3: Check if realtime is supported
        print("\n[3] Checking realtime usage support...")
        if opower_client.utility.supports_realtime_usage():
            print("    ✓ Realtime usage is supported for Con Edison")
        else:
            print("    ✗ Realtime usage NOT supported")

        # Step 4: Get realtime usage
        print("\n[4] Fetching realtime usage reads...")
        try:
            realtime_reads = await opower_client.async_get_realtime_usage_reads(account)
            print(f"    ✓ Got {len(realtime_reads)} realtime reading(s)")
            
            if realtime_reads:
                print("\n    --- RAW REALTIME DATA ---")
                for i, read in enumerate(realtime_reads[-10:]):  # Last 10 readings
                    print(f"    [{i+1}] {read.start_time} - {read.end_time}: {read.consumption:.4f} kWh")
                
                latest = realtime_reads[-1]
                print(f"\n    LATEST READING:")
                print(f"      Start: {latest.start_time}")
                print(f"      End: {latest.end_time}")
                print(f"      Consumption: {latest.consumption:.4f} kWh")
                
                # Convert to JSON-serializable format
                raw_data = {
                    "latest": {
                        "start_time": latest.start_time.isoformat(),
                        "end_time": latest.end_time.isoformat(),
                        "consumption": latest.consumption,
                        "unit": "kWh"
                    },
                    "all_reads": [
                        {
                            "start_time": r.start_time.isoformat(),
                            "end_time": r.end_time.isoformat(),
                            "consumption": r.consumption
                        }
                        for r in realtime_reads
                    ]
                }
                print(f"\n    --- JSON OUTPUT ---")
                print(json.dumps(raw_data, indent=2))
            else:
                print("    No realtime readings available")
        except Exception as e:
            print(f"    ✗ Failed to get realtime reads: {e}")
            import traceback
            traceback.print_exc()

        # Step 5: Get forecast
        print("\n[5] Fetching forecast data...")
        try:
            forecasts = await opower_client.async_get_forecast()
            print(f"    ✓ Got {len(forecasts)} forecast(s)")
            
            for forecast in forecasts:
                print(f"\n    Forecast for {forecast.account.utility_account_id}:")
                print(f"      Period: {forecast.start_date} to {forecast.end_date}")
                print(f"      Current Date: {forecast.current_date}")
                print(f"      Unit: {forecast.unit_of_measure}")
                print(f"      Usage to Date: {forecast.usage_to_date:.2f}")
                print(f"      Cost to Date: ${forecast.cost_to_date:.2f}")
                print(f"      Forecasted Usage: {forecast.forecasted_usage:.2f}")
                print(f"      Forecasted Cost: ${forecast.forecasted_cost:.2f}")
                print(f"      Typical Usage: {forecast.typical_usage:.2f}")
                print(f"      Typical Cost: ${forecast.typical_cost:.2f}")
        except Exception as e:
            print(f"    ✗ Failed to get forecast: {e}")

        # Step 6: Get recent daily usage
        print("\n[6] Fetching recent daily usage (last 7 days)...")
        try:
            from datetime import timezone
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
            
            daily_reads = await opower_client.async_get_cost_reads(
                account,
                AggregateType.DAY,
                start_date,
                end_date
            )
            print(f"    ✓ Got {len(daily_reads)} daily reading(s)")
            
            for read in daily_reads:
                print(f"      {read.start_time.date()}: {read.consumption:.2f} kWh, ${read.provided_cost:.2f}")
        except Exception as e:
            print(f"    ✗ Failed to get daily reads: {e}")

        # Step 7: Get billing history
        print("\n[7] Fetching billing history...")
        try:
            bill_reads = await opower_client.async_get_cost_reads(
                account,
                AggregateType.BILL
            )
            print(f"    ✓ Got {len(bill_reads)} billing period(s)")
            
            for read in bill_reads[-6:]:  # Last 6 bills
                print(f"      {read.start_time.date()} to {read.end_time.date()}: {read.consumption:.2f} kWh, ${read.provided_cost:.2f}")
        except Exception as e:
            print(f"    ✗ Failed to get billing reads: {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Test opower library with Con Edison")
    parser.add_argument("--email", "-e", help="Con Edison email", 
                        default=os.getenv("CONED_EMAIL"))
    parser.add_argument("--password", "-p", help="Con Edison password",
                        default=os.getenv("CONED_PASSWORD"))
    parser.add_argument("--totp-secret", "-t", help="TOTP secret for MFA",
                        default=os.getenv("CONED_TOTP_SECRET"))
    
    args = parser.parse_args()
    
    if not args.email or not args.password:
        print("ERROR: Email and password are required.")
        print()
        print("Usage:")
        print("  python test_opower.py --email YOUR_EMAIL --password YOUR_PASSWORD --totp-secret YOUR_TOTP_SECRET")
        print()
        print("Or set environment variables:")
        print("  CONED_EMAIL, CONED_PASSWORD, CONED_TOTP_SECRET")
        sys.exit(1)
    
    asyncio.run(test_opower(args.email, args.password, args.totp_secret or ""))


if __name__ == "__main__":
    main()
