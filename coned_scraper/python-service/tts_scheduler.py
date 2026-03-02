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
        if TTS_SCHEDULE_FILE.exists():
            try:
                return json.loads(TTS_SCHEDULE_FILE.read_text())
            except Exception as e:
                logger.error(f"Failed to load TTS schedule config: {e}")
        return {
            "enabled": False,
            "schedule_times": [],  # List of {"time": "08:00", "days": ["mon", "tue", ...]}
            "schedule_type": "daily",  # "daily", "specific_days"
            "updated_at": None
        }
    
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
        """Check if any scheduled TTS should be triggered."""
        schedule_config = self.load_schedule_config()
        tts_config = self.load_tts_config()
        
        if not schedule_config.get("enabled"):
            return
        
        if not tts_config.get("enabled"):
            return
        
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        current_day = now.weekday()  # 0 = Monday
        current_day_abbr = list(DAY_MAP.keys())[current_day]
        
        for schedule_item in schedule_config.get("schedule_times", []):
            trigger_time = schedule_item.get("time", "")
            allowed_days = schedule_item.get("days", [])
            
            # Parse trigger time
            if not trigger_time:
                continue
            
            # Check if we should trigger
            if trigger_time != current_time_str:
                continue
            
            # Check day filter
            if allowed_days and current_day_abbr not in [d.lower()[:3] for d in allowed_days]:
                continue
            
            # Prevent duplicate triggers within the same minute
            trigger_key = f"{trigger_time}_{current_day}"
            last_trigger = self._last_triggered.get(trigger_key)
            if last_trigger and (now - last_trigger).total_seconds() < 120:
                continue
            
            # Trigger the TTS
            self._last_triggered[trigger_key] = now
            logger.info(f"Triggering scheduled TTS at {trigger_time}")
            
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
        """Build the bill summary TTS message using ledger data."""
        try:
            from database import get_ledger_data
            
            ledger = get_ledger_data()
            balance = ledger.get("account_balance", "")
            latest_bill = ledger.get("latest_bill", {})
            latest_payment = ledger.get("latest_payment", {})
            
            parts = []
            
            # Current balance
            if balance:
                parts.append(f"Your current Con Edison balance is {balance}.")
            
            # Latest bill info
            if latest_bill:
                bill_total = latest_bill.get("bill_total", "")
                month_range = latest_bill.get("month_range", "")
                if bill_total and month_range:
                    parts.append(f"Your latest bill for {month_range} is {bill_total}.")
            
            # Latest payment info
            if latest_payment:
                amount = latest_payment.get("amount", "")
                payee_name = latest_payment.get("payee_name", "")
                payment_date = latest_payment.get("payment_date", "")
                if amount:
                    payee_str = f"from {payee_name}" if payee_name else ""
                    date_str = f"on {payment_date}" if payment_date else ""
                    parts.append(f"Your last payment was {amount} {payee_str} {date_str}.".replace("  ", " "))
            
            if not parts:
                return "No billing information is currently available."
            
            return " ".join(parts)
        except Exception as e:
            logger.error(f"Error building bill summary message: {e}")
            return ""


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
