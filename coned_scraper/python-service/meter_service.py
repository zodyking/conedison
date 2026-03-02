"""
Meter Service for Real-Time Con Edison Meter Readings

Uses the opower library (https://github.com/tronikos/opower) to fetch
real-time meter readings from Con Edison's Opower API.

The opower library is the same one used by Home Assistant's official
Opower integration and supports Con Edison with TOTP MFA.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import aiohttp

logger = logging.getLogger(__name__)

# Singleton instance
_meter_service: Optional['MeterService'] = None


class MeterService:
    """Service for fetching and caching meter readings from Con Edison via Opower."""
    
    def __init__(self):
        self.last_reading: Optional[Dict[str, Any]] = None
        self.last_reading_time: Optional[datetime] = None
        self.config: Optional[Dict[str, Any]] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._running = False
        self._opower = None
        self._accounts: List[Any] = []
    
    def is_configured(self) -> bool:
        """Check if meter service is properly configured.
        
        Requires email, password, and totp_secret for opower/ConEd authentication.
        """
        if not self.config:
            return False
        # opower ConEd requires: email, password, totp_secret
        required = ['email', 'password', 'totp_secret']
        return all(self.config.get(k) for k in required)
    
    def is_enabled(self) -> bool:
        """Check if meter tracking is enabled."""
        return self.config and self.config.get('enabled', False) and self.is_configured()
    
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize meter with configuration from database."""
        try:
            from opower import Opower
            from opower.utilities.coned import ConEd
            
            self.config = config
            
            if not self.is_configured():
                logger.warning("Meter service not fully configured")
                return False
            
            # Decrypt password if encrypted
            password = config.get('password', '')
            if password and not password.startswith('plain:'):
                try:
                    from main import decrypt_data
                    password = decrypt_data(password)
                except Exception:
                    pass
            
            # Initialize opower with ConEd utility
            self._opower = Opower(
                session=aiohttp.ClientSession(),
                utility=ConEd(totp_secret=config.get('totp_secret', '')),
                username=config['email'],
                password=password,
            )
            
            logger.info("Meter service initialized (opower/ConEd)")
            return True
            
        except ImportError as e:
            logger.error(f"opower library not installed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize meter service: {e}")
            return False
    
    async def _login(self) -> bool:
        """Login to Con Edison via opower."""
        if not self._opower:
            return False
        
        try:
            await self._opower.async_login()
            logger.info("Logged in to Con Edison via opower")
            return True
        except Exception as e:
            logger.error(f"Opower login failed: {e}")
            return False
    
    async def _get_accounts(self) -> List[Any]:
        """Get accounts from opower."""
        if not self._opower:
            return []
        
        if not self._accounts:
            try:
                self._accounts = await self._opower.async_get_accounts()
                logger.info(f"Found {len(self._accounts)} opower account(s)")
            except Exception as e:
                logger.error(f"Failed to get opower accounts: {e}")
        
        return self._accounts
    
    async def fetch_reading(self) -> Optional[Dict[str, Any]]:
        """Fetch the latest meter reading from Con Edison (opower realtime API)."""
        if not self.is_configured():
            logger.error("Meter not configured")
            return None
        
        try:
            # Login if needed
            if not await self._login():
                return None
            
            # Get accounts
            accounts = await self._get_accounts()
            if not accounts:
                logger.error("No opower accounts found")
                return None
            
            # Get realtime usage for first electric account
            account = accounts[0]
            
            # Check if utility supports realtime
            if not self._opower.utility.supports_realtime_usage():
                logger.warning("Con Edison doesn't support realtime usage in this account")
                return None
            
            reads = await self._opower.async_get_realtime_usage_reads(account)
            
            if not reads:
                logger.warning("No realtime readings available")
                return None
            
            # Get the most recent reading
            latest = reads[-1]  # Last entry is most recent
            
            reading = {
                'start_time': latest.start_time.isoformat() if latest.start_time else None,
                'end_time': latest.end_time.isoformat() if latest.end_time else None,
                'value': float(latest.consumption) if latest.consumption is not None else None,
                'unit': 'kWh',
                'fetched_at': datetime.now(timezone.utc).isoformat()
            }
            
            self.last_reading = reading
            self.last_reading_time = datetime.now(timezone.utc)
            
            # Cache to database
            from database import save_meter_reading_db
            save_meter_reading_db(reading)
            
            logger.info(f"Meter reading fetched: {reading['value']} {reading['unit']}")
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
        
        # Close opower session
        if self._opower and hasattr(self._opower, '_session') and self._opower._session:
            await self._opower._session.close()
        
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
        # Decrypt password for opower
        if config.get('password'):
            try:
                from main import decrypt_data
                config['password'] = decrypt_data(config['password'])
            except Exception:
                pass
        
        success = await service.initialize(config)
        if success:
            interval = config.get('polling_interval', 15)
            await service.start_polling(interval)
            return True
    
    return False
