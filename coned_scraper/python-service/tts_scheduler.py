"""
TTS Scheduler for Con Edison Addon.
Handles scheduled TTS announcements including:
- Scheduled bill summary announcements (daily/weekly)
- Time-based triggers with day filtering
- Event-triggered TTS for new bills and payments
"""
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Callable, Optional, Dict, Any, List
from pathlib import Path
import json

logger = logging.getLogger(__name__)

DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent / "data"
TTS_SCHEDULE_FILE = DATA_DIR / "tts_schedule.json"
TTS_CONFIG_FILE = DATA_DIR / "tts_config.json"

DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

class TTSScheduler:
    """Manages scheduled TTS announcements."""
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_triggered: Dict[str, datetime] = {}
    
    def load_schedule_config(self) -> Dict[str, Any]:
        """Load TTS schedule configuration."""
        defaults = {
            "enabled": False,
            "hour_pattern": 3,  # Announce every N hours
            "minute_offset": 0,  # Minute within hour (e.g., :00, :30)
            "start_time": "08:00",  # Active hours start
            "end_time": "21:00",  # Active hours end
            "days_of_week": ["mon", "tue", "wed", "thu", "fri"],
            "message_template": "{greeting}. It is currently {time}. Your Con Edison account balance is {balance}. Your most recent bill for {latest_bill_period} totaled {latest_bill_amount} and is due {due_date}. You used {kwh_used} of electricity this billing cycle. Your last payment of {last_payment_amount} was received on {last_payment_date}.",
            "kwh_sensor": "",  # HA sensor entity for kWh usage
            "schedule_times": [],  # Legacy: List of {"time": "08:00", "days": ["mon", "tue", ...]}
            "schedule_type": "daily",  # Legacy
            "updated_at": None
        }
        if TTS_SCHEDULE_FILE.exists():
            try:
                data = json.loads(TTS_SCHEDULE_FILE.read_text())
                return {**defaults, **data}
            except Exception as e:
                logger.error(f"Failed to load TTS schedule config: {e}")
        return defaults
    
    def save_schedule_config(self, config: Dict[str, Any]):
        """Save TTS schedule configuration."""
        config["updated_at"] = datetime.utcnow().isoformat() + "Z"
        TTS_SCHEDULE_FILE.write_text(json.dumps(config, indent=2))
    
    def load_tts_config(self) -> Dict[str, Any]:
        """Load TTS configuration."""
        if TTS_CONFIG_FILE.exists():
            try:
                return json.loads(TTS_CONFIG_FILE.read_text())
            except Exception:
                pass
        return {}
    
    async def start(self):
        """Start the TTS scheduler loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("TTS scheduler started")
    
    async def stop(self):
        """Stop the TTS scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TTS scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop - checks every minute for scheduled TTS."""
        while self._running:
            try:
                await self._check_and_trigger()
            except Exception as e:
                logger.error(f"TTS scheduler error: {e}")
            
            await asyncio.sleep(60)  # Check every minute
    
    async def _check_and_trigger(self):
        """Check if any scheduled TTS should be triggered.
        
        Uses home-weather style scheduling:
        - hour_pattern: Announce every N hours (1, 2, 3, 4, 6, 12)
        - minute_offset: The minute within the hour to trigger (0-59)
        - start_time/end_time: Active hours window
        - days_of_week: Active days
        """
        schedule_config = self.load_schedule_config()
        tts_config = self.load_tts_config()
        
        if not schedule_config.get("enabled"):
            return
        
        if not tts_config.get("enabled"):
            return
        
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_day = now.weekday()  # 0 = Monday
        current_day_abbr = list(DAY_MAP.keys())[current_day]
        
        # Check day filter
        days_of_week = schedule_config.get("days_of_week", [])
        if days_of_week and current_day_abbr not in [d.lower()[:3] for d in days_of_week]:
            return
        
        # Check active hours
        start_time_str = schedule_config.get("start_time", "08:00")
        end_time_str = schedule_config.get("end_time", "21:00")
        
        try:
            start_h, start_m = map(int, start_time_str.split(":"))
            end_h, end_m = map(int, end_time_str.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m
            current_minutes = current_hour * 60 + current_minute
            
            if not (start_minutes <= current_minutes <= end_minutes):
                return
        except Exception:
            pass  # If parsing fails, proceed anyway
        
        # Check hour pattern - only trigger at hours that match the pattern
        hour_pattern = schedule_config.get("hour_pattern", 3)
        minute_offset = schedule_config.get("minute_offset", 0)
        
        # Generate trigger hours based on pattern (e.g., every 3 hours: 0, 3, 6, 9, 12, 15, 18, 21)
        trigger_hours = list(range(0, 24, hour_pattern))
        
        if current_hour not in trigger_hours:
            return
        
        if current_minute != minute_offset:
            return
        
        # Prevent duplicate triggers within the same minute
        trigger_key = f"pattern_{current_hour}_{current_minute}_{current_day}"
        last_trigger = self._last_triggered.get(trigger_key)
        if last_trigger and (now - last_trigger).total_seconds() < 120:
            return
        
        # Trigger the TTS
        self._last_triggered[trigger_key] = now
        logger.info(f"Triggering scheduled TTS at {current_hour}:{current_minute:02d}")
        
        await self._send_scheduled_tts(tts_config)
    
    async def _send_scheduled_tts(self, tts_config: Dict[str, Any]):
        """Send the scheduled TTS announcement."""
        from ha_tts import send_tts
        
        media_player = tts_config.get("media_player", "").strip()
        if not media_player:
            logger.warning("No media player configured for scheduled TTS")
            return
        
        message = await self._build_bill_summary_message()
        if not message:
            logger.warning("No TTS message generated")
            return
        
        prefix = tts_config.get("prefix", "Message from Con Edison.")
        full_message = f"{prefix}, {message}" if prefix else message
        
        volume = tts_config.get("volume", 0.7)
        wait_for_idle = tts_config.get("wait_for_idle", True)
        tts_service = tts_config.get("tts_service", "tts.google_translate_say")
        
        try:
            success, err = await send_tts(
                message=full_message,
                media_player=media_player,
                volume=volume,
                wait_for_idle=wait_for_idle,
                tts_service=tts_service,
            )
            if success:
                logger.info("Scheduled TTS sent successfully")
            else:
                logger.error(f"Scheduled TTS failed: {err}")
        except Exception as e:
            logger.error(f"Error sending scheduled TTS: {e}")
    
    async def _build_bill_summary_message(self) -> str:
        """Build the bill summary TTS message using ledger data and message template."""
        try:
            from database import get_ledger_data, get_latest_bill_with_details
            import aiohttp
            import os
            
            schedule_config = self.load_schedule_config()
            template = schedule_config.get("message_template", "")
            kwh_sensor = schedule_config.get("kwh_sensor", "")
            
            if not template:
                template = "{greeting}. It is currently {time}. Your Con Edison account balance is {balance}."
            
            ledger = get_ledger_data()
            bill_details = get_latest_bill_with_details()
            
            # Get current time info
            now = datetime.now()
            hour = now.hour
            if 5 <= hour < 12:
                greeting = "Good morning"
            elif 12 <= hour < 17:
                greeting = "Good afternoon"
            elif 17 <= hour < 21:
                greeting = "Good evening"
            else:
                greeting = "Good night"
            
            hour_12 = hour % 12 or 12
            minute = now.minute
            period = "AM" if hour < 12 else "PM"
            if minute == 0:
                time_str = f"{hour_12} {period}"
            elif minute < 10:
                time_str = f"{hour_12} oh {minute} {period}"
            else:
                time_str = f"{hour_12} {minute} {period}"
            
            # Get balance from ledger
            balance = ledger.get("account_balance") or ledger.get("total_balance", "")
            if isinstance(balance, (int, float)):
                balance = f"${balance:.2f}"
            
            # Get latest bill data from ledger
            bills = ledger.get("bills", [])
            latest_bill = bills[0] if bills else {}
            
            bill_amount = latest_bill.get("amount", "") or latest_bill.get("bill_total", "")
            bill_period = latest_bill.get("month_range", "")
            
            # Get due_date and kwh from bill_details table
            due_date = ""
            kwh_used = ""
            
            if bill_details:
                due_date = bill_details.get("due_date", "") or ""
                kwh_val = bill_details.get("kwh_used")
                if kwh_val:
                    kwh_used = f"{kwh_val} kWh"
                if not bill_amount:
                    bill_amount = bill_details.get("amount", "")
                if not bill_period:
                    bill_period = bill_details.get("month_range", "")
            
            # If kwh_sensor is configured, try to fetch from Home Assistant
            if kwh_sensor and kwh_sensor.strip():
                token = os.environ.get("SUPERVISOR_TOKEN")
                if token:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                f"http://supervisor/core/api/states/{kwh_sensor.strip()}",
                                headers={"Authorization": f"Bearer {token}"},
                            ) as resp:
                                if resp.status == 200:
                                    state_data = await resp.json()
                                    sensor_state = state_data.get("state", "")
                                    unit = state_data.get("attributes", {}).get("unit_of_measurement", "kWh")
                                    if sensor_state and sensor_state not in ("unknown", "unavailable"):
                                        kwh_used = f"{sensor_state} {unit}"
                    except Exception as e:
                        logger.warning(f"Failed to fetch kWh sensor: {e}")
            
            # Get latest payment from ledger
            latest_payment = ledger.get("latest_payment")
            last_payment_amount = ""
            last_payment_date = ""
            
            if latest_payment and isinstance(latest_payment, dict):
                last_payment_amount = latest_payment.get("amount", "")
                last_payment_date = latest_payment.get("payment_date", "")
            
            # Build placeholder values
            placeholders = {
                "greeting": greeting,
                "time": time_str,
                "balance": balance or "N/A",
                "latest_bill_amount": bill_amount or "N/A",
                "latest_bill_period": bill_period or "N/A",
                "due_date": due_date or "N/A",
                "last_payment_amount": last_payment_amount or "No payment",
                "last_payment_date": last_payment_date or "N/A",
                "kwh_used": kwh_used or "N/A",
            }
            
            # Replace placeholders in template
            message = template
            for key, value in placeholders.items():
                message = message.replace(f"{{{key}}}", str(value) if value else "N/A")
            
            return message
        except Exception as e:
            logger.error(f"Error building bill summary message: {e}")
            return "Your Con Edison bill summary is currently unavailable."


# Global scheduler instance
_scheduler: Optional[TTSScheduler] = None

def get_scheduler() -> TTSScheduler:
    """Get or create the global TTS scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TTSScheduler()
    return _scheduler


async def trigger_new_bill_tts(bill_month_range: str, bill_total: str):
    """Trigger TTS for a new bill."""
    scheduler = get_scheduler()
    tts_config = scheduler.load_tts_config()
    
    if not tts_config.get("enabled"):
        return
    
    media_player = tts_config.get("media_player", "").strip()
    if not media_player:
        return
    
    template = tts_config.get("messages", {}).get("new_bill", "")
    if not template:
        template = "Your new Con Edison bill for {month_range} is now available. The total is {bill_total}."
    
    try:
        message = template.format(month_range=bill_month_range, bill_total=bill_total)
    except KeyError:
        message = template
    
    prefix = tts_config.get("prefix", "Message from Con Edison.")
    full_message = f"{prefix}, {message}" if prefix else message
    
    from ha_tts import send_tts
    
    try:
        await send_tts(
            message=full_message,
            media_player=media_player,
            volume=tts_config.get("volume", 0.7),
            wait_for_idle=tts_config.get("wait_for_idle", True),
            tts_service=tts_config.get("tts_service", "tts.google_translate_say"),
        )
        logger.info("New bill TTS sent successfully")
    except Exception as e:
        logger.error(f"Error sending new bill TTS: {e}")


async def trigger_payment_received_tts(amount: str, balance: str, payee_name: str = ""):
    """Trigger TTS for a payment received."""
    scheduler = get_scheduler()
    tts_config = scheduler.load_tts_config()
    
    if not tts_config.get("enabled"):
        return
    
    media_player = tts_config.get("media_player", "").strip()
    if not media_player:
        return
    
    template = tts_config.get("messages", {}).get("payment_received", "")
    if not template:
        template = "Good news — your payment of {amount} has been received. Your account balance is now {balance}."
    
    try:
        message = template.format(amount=amount, balance=balance, payee_name=payee_name)
    except KeyError:
        message = template
    
    prefix = tts_config.get("prefix", "Message from Con Edison.")
    full_message = f"{prefix}, {message}" if prefix else message
    
    from ha_tts import send_tts
    
    try:
        await send_tts(
            message=full_message,
            media_player=media_player,
            volume=tts_config.get("volume", 0.7),
            wait_for_idle=tts_config.get("wait_for_idle", True),
            tts_service=tts_config.get("tts_service", "tts.google_translate_say"),
        )
        logger.info("Payment received TTS sent successfully")
    except Exception as e:
        logger.error(f"Error sending payment TTS: {e}")
