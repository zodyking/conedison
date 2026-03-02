"""
Meter Service for Real-Time Con Edison Meter Readings

Uses the coned library (https://github.com/bvlaicu/coned) to fetch
near real-time meter readings from Con Edison smart meters.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Singleton instance
_meter_service: Optional['MeterService'] = None


class MeterService:
    """Service for fetching and caching meter readings from Con Edison."""
    
    def __init__(self):
        self.meter = None
        self.last_reading: Optional[Dict[str, Any]] = None
        self.last_reading_time: Optional[datetime] = None
        self.config: Optional[Dict[str, Any]] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._running = False
    
    def is_configured(self) -> bool:
        """Check if meter service is properly configured."""
        if not self.config:
            return False
        required = ['email', 'password', 'mfa_secret', 'account_uuid', 'meter_number']
        return all(self.config.get(k) for k in required)
    
    def is_enabled(self) -> bool:
        """Check if meter tracking is enabled."""
        return self.config and self.config.get('enabled', False) and self.is_configured()
    
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize meter with configuration from database."""
        try:
            from coned import Meter
            
            self.config = config
            
            if not self.is_configured():
                logger.warning("Meter service not fully configured")
                return False
            
            mfa_type_str = config.get('mfa_type', 'totp').lower()
            mfa_type = Meter.TOTP if mfa_type_str == 'totp' else Meter.SECURITY_QUESTION
            
            self.meter = Meter(
                email=config['email'],
                password=config['password'],
                mfa_type=mfa_type,
                mfa_secret=config['mfa_secret'],
                account_uuid=config['account_uuid'],
                meter_number=config['meter_number'],
                site=Meter.SITE_CONED
            )
            
            logger.info("Meter service initialized successfully")
            return True
            
        except ImportError:
            logger.error("coned library not installed. Run: pip install coned")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize meter service: {e}")
            return False
    
    async def fetch_reading(self) -> Optional[Dict[str, Any]]:
        """Fetch the latest meter reading from Con Edison."""
        if not self.meter:
            logger.error("Meter not initialized")
            return None
        
        try:
            start_time, end_time, value, unit = await self.meter.last_read()
            
            reading = {
                'start_time': str(start_time) if start_time else None,
                'end_time': str(end_time) if end_time else None,
                'value': float(value) if value is not None else None,
                'unit': unit or 'kWh',
                'fetched_at': datetime.now(timezone.utc).isoformat()
            }
            
            self.last_reading = reading
            self.last_reading_time = datetime.now(timezone.utc)
            
            # Cache to database
            from database import save_meter_reading_db
            save_meter_reading_db(reading)
            
            logger.info(f"Meter reading fetched: {value} {unit}")
            return reading
            
        except Exception as e:
            logger.error(f"Failed to fetch meter reading: {e}")
            return None
    
    def get_cached_reading(self) -> Optional[Dict[str, Any]]:
        """Get the most recent cached reading."""
        if self.last_reading:
            return self.last_reading
        
        # Try to load from database
        from database import get_meter_reading_db
        cached = get_meter_reading_db()
        if cached:
            self.last_reading = cached
            return cached
        
        return None
    
    async def start_polling(self, interval_minutes: int = 15):
        """Start background polling for meter readings."""
        if self._running:
            logger.warning("Meter polling already running")
            return
        
        self._running = True
        interval_seconds = interval_minutes * 60
        
        async def poll_loop():
            while self._running:
                try:
                    if self.is_enabled():
                        reading = await self.fetch_reading()
                        if reading:
                            # Publish to MQTT
                            await self._publish_reading(reading)
                except Exception as e:
                    logger.error(f"Meter polling error: {e}")
                
                await asyncio.sleep(interval_seconds)
        
        self._polling_task = asyncio.create_task(poll_loop())
        logger.info(f"Meter polling started (interval: {interval_minutes} minutes)")
    
    async def stop_polling(self):
        """Stop background polling."""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
        logger.info("Meter polling stopped")
    
    async def _publish_reading(self, reading: Dict[str, Any]):
        """Publish meter reading to MQTT sensors."""
        try:
            from mqtt_client import get_mqtt_client
            from database import get_latest_bill_with_details
            
            mqtt_client = get_mqtt_client()
            if not mqtt_client:
                return
            
            value = reading.get('value')
            unit = reading.get('unit', 'kWh')
            timestamp = reading.get('fetched_at')
            
            if value is None:
                return
            
            # Publish current meter usage
            await mqtt_client.publish_current_meter_usage(value, unit, timestamp)
            
            # Calculate and publish cost
            latest_bill = get_latest_bill_with_details()
            if latest_bill and latest_bill.get('kwh_cost'):
                kwh_cost = float(latest_bill['kwh_cost'])
                usage_cost = value * kwh_cost
                await mqtt_client.publish_current_usage_cost(usage_cost, timestamp)
            
        except Exception as e:
            logger.error(f"Failed to publish meter reading to MQTT: {e}")


def get_meter_service() -> MeterService:
    """Get or create the singleton meter service instance."""
    global _meter_service
    if _meter_service is None:
        _meter_service = MeterService()
    return _meter_service


async def init_meter_service():
    """Initialize meter service from database config."""
    from database import get_meter_config_db
    
    service = get_meter_service()
    config = get_meter_config_db()
    
    if config and config.get('enabled'):
        success = await service.initialize(config)
        if success:
            interval = config.get('polling_interval', 15)
            await service.start_polling(interval)
            return True
    
    return False
