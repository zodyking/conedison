#!/usr/bin/env python3
"""
Test script for opower library with Con Edison.

Uses the same approach as opower's built-in CLI to ensure proper authentication flow.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone


async def test_opower(email: str, password: str, totp_secret: str):
    """Test opower library with Con Edison credentials."""
    
    try:
        import aiohttp
        from opower import Opower, AggregateType, create_cookie_jar
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

    # Use opower's cookie jar (required for proper session handling)
    async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
        # Initialize opower
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
            print(f"    Access token received: {'Yes' if opower_client.access_token else 'No'}")
        except Exception as e:
            print(f"    ✗ Login failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # Step 2: Get forecast (this also fetches accounts internally)
        print("\n[2] Fetching forecast (includes account discovery)...")
        try:
            forecasts = await opower_client.async_get_forecast()
            print(f"    ✓ Got {len(forecasts)} forecast(s)")
            
            for forecast in forecasts:
                account = forecast.account
                print(f"\n    Account: {account.utility_account_id}")
                print(f"      UUID: {account.uuid}")
                print(f"      Meter Type: {account.meter_type}")
                print(f"      Resolution: {account.read_resolution}")
                print(f"      Period: {forecast.start_date} to {forecast.end_date}")
                print(f"      Usage to Date: {forecast.usage_to_date} {forecast.unit_of_measure}")
                print(f"      Forecasted Usage: {forecast.forecasted_usage} {forecast.unit_of_measure}")
                print(f"      Cost to Date: ${forecast.cost_to_date:.2f}")
                print(f"      Forecasted Cost: ${forecast.forecasted_cost:.2f}")
        except Exception as e:
            print(f"    ✗ Failed to get forecast: {e}")
            import traceback
            traceback.print_exc()
            return

        if not forecasts:
            print("    No forecasts/accounts found!")
            return

        # Use the first account
        account = forecasts[0].account
        print(f"\n    Using account: {account.utility_account_id}")

        # Step 3: Get hourly usage (last 7 days - max for hourly)
        print("\n[3] Fetching hourly usage reads (last 7 days)...")
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
            
            hourly_reads = await opower_client.async_get_cost_reads(
                account,
                AggregateType.HOUR,
                start_date,
                end_date
            )
            print(f"    ✓ Got {len(hourly_reads)} hourly reading(s)")
            
            if hourly_reads:
                print("\n    --- HOURLY DATA (last 10 hours) ---")
                for i, read in enumerate(hourly_reads[-10:]):
                    print(f"    [{i+1}] {read.start_time} - {read.end_time}: {read.consumption:.3f} kWh")
                
                latest = hourly_reads[-1]
                print(f"\n    LATEST READING:")
                print(f"      Start: {latest.start_time}")
                print(f"      End: {latest.end_time}")
                print(f"      Consumption: {latest.consumption:.4f} kWh")
            else:
                print("    No hourly readings available")
        except Exception as e:
            print(f"    ✗ Failed to get hourly reads: {e}")
            import traceback
            traceback.print_exc()
            hourly_reads = []

        # Step 4: Get daily usage (last 365 days - max for daily)
        print("\n[4] Fetching daily usage (last 365 days)...")
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=365)
            
            daily_reads = await opower_client.async_get_cost_reads(
                account,
                AggregateType.DAY,
                start_date,
                end_date
            )
            print(f"    ✓ Got {len(daily_reads)} daily reading(s)")
            
            # Show last 7 days
            print("\n    --- DAILY DATA (last 7 days) ---")
            for read in daily_reads[-7:]:
                print(f"      {read.start_time.date()}: {read.consumption:.2f} kWh")
        except Exception as e:
            print(f"    ✗ Failed to get daily reads: {e}")
            daily_reads = []

        # Step 5: Get billing history (all available)
        print("\n[5] Fetching billing history (all available)...")
        try:
            bill_reads = await opower_client.async_get_cost_reads(
                account,
                AggregateType.BILL
            )
            print(f"    ✓ Got {len(bill_reads)} billing period(s)")
            
            for read in bill_reads:
                print(f"      {read.start_time.date()} to {read.end_time.date()}: {read.consumption:.2f} kWh")
        except Exception as e:
            print(f"    ✗ Failed to get billing reads: {e}")
            bill_reads = []

        # Step 6: Save all data to JSON file
        print("\n[6] Saving all data to opower_data.json...")
        try:
            output_data = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "account": {
                    "utility_account_id": account.utility_account_id,
                    "uuid": account.uuid,
                    "meter_type": str(account.meter_type),
                    "read_resolution": str(account.read_resolution),
                    "customer_uuid": account.customer.uuid if account.customer else None
                },
                "forecast": {
                    "start_date": forecasts[0].start_date.isoformat() if forecasts else None,
                    "end_date": forecasts[0].end_date.isoformat() if forecasts else None,
                    "usage_to_date": forecasts[0].usage_to_date if forecasts else None,
                    "forecasted_usage": forecasts[0].forecasted_usage if forecasts else None,
                    "cost_to_date": forecasts[0].cost_to_date if forecasts else None,
                    "forecasted_cost": forecasts[0].forecasted_cost if forecasts else None,
                    "unit": str(forecasts[0].unit_of_measure) if forecasts else None
                },
                "hourly_reads": [
                    {
                        "start_time": r.start_time.isoformat(),
                        "end_time": r.end_time.isoformat(),
                        "consumption": r.consumption,
                        "provided_cost": r.provided_cost
                    }
                    for r in hourly_reads
                ],
                "daily_reads": [
                    {
                        "start_time": r.start_time.isoformat(),
                        "end_time": r.end_time.isoformat(),
                        "consumption": r.consumption,
                        "provided_cost": r.provided_cost
                    }
                    for r in daily_reads
                ],
                "bill_reads": [
                    {
                        "start_time": r.start_time.isoformat(),
                        "end_time": r.end_time.isoformat(),
                        "consumption": r.consumption,
                        "provided_cost": r.provided_cost
                    }
                    for r in bill_reads
                ]
            }
            
            output_file = "opower_data.json"
            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2)
            
            print(f"    ✓ Saved to {output_file}")
            print(f"      - {len(hourly_reads)} hourly reads")
            print(f"      - {len(daily_reads)} daily reads")
            print(f"      - {len(bill_reads)} billing periods")
        except Exception as e:
            print(f"    ✗ Failed to save data: {e}")

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
