import heapq
import time
import threading
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from models import Session as DBSession, ApiKey

logger = logging.getLogger(__name__)

class AdvancedKeyManager:
    """
    Manages API keys using a Priority Queue (Max Heap) and 'Sync by Request' strategy.
    Optimized for multi-threaded environments handling hundreds of keys.
    """
    def __init__(self, sync_interval_seconds=60):
        self._heap = []  # Elements: (-score, last_used_timestamp, key_data_dict)
        self._lock = threading.Lock()
        self._last_sync_time = 0
        self.sync_interval = sync_interval_seconds
        
        # Initial sync
        self.sync()

    def sync(self, force=False):
        """Synchronizes the local heap with the database."""
        now = time.time()
        
        with self._lock:
            # Check if sync is needed
            if not force and (now - self._last_sync_time) < self.sync_interval:
                return

            self._last_sync_time = now
            
            try:
                with DBSession() as db:
                    current_time_iso = datetime.utcnow().isoformat()
                    
                    # 1. Recover keys that passed their cooldown
                    recovering_keys = db.query(ApiKey).filter(
                        ApiKey.status == 'RATE_LIMITED',
                        ApiKey.cooldown_until <= current_time_iso
                    ).all()
                    
                    for key in recovering_keys:
                        key.status = 'ACTIVE'
                        key.cooldown_until = None
                        logger.info(f"[KeyManager] Key {key.id} recovered from RATE_LIMITED.")
                    
                    if recovering_keys:
                        db.commit()

                    # 2. Fetch all ACTIVE keys
                    active_keys = db.query(ApiKey).filter(ApiKey.status == 'ACTIVE').all()
                    
                    # Rebuild heap entirely to ensure consistency
                    self._heap = []
                    for k in active_keys:
                        # Initial score is just the weight. 
                        # We negate the score because heapq is a Min-Heap, so -weight makes higher weights pop first.
                        score = k.weight
                        key_data = {
                            'id': k.id,
                            'key_value': k.key_value,
                            'provider': k.provider,
                            'weight': k.weight
                        }
                        heapq.heappush(self._heap, (-score, 0, k.id, key_data))
                
                logger.info(f"[KeyManager] Synced with DB. Local pool size: {len(self._heap)} keys.")
            except Exception as e:
                logger.error(f"[KeyManager] Failed to sync keys from DB: {e}")

    def get_best_key(self):
        """Pops the healthiest key from the Priority Queue."""
        # Opportunistic sync
        self.sync()
        
        with self._lock:
            if not self._heap:
                # Force sync if empty to see if cooldowns expired
                self._lock.release() # Release lock before calling sync to avoid deadlock
                self.sync(force=True)
                self._lock.acquire() # Reacquire
                
                if not self._heap:
                    raise Exception("No active API keys available in the pool. All might be rate limited or invalid.")

            neg_score, last_used, k_id, key_data = heapq.heappop(self._heap)
            
            # Key is now "checked out". It's not in the heap.
            return key_data

    def release_key(self, key_data, success=True):
        """Returns the key to the Priority Queue with an adjusted score."""
        with self._lock:
            # We decay the score slightly so it doesn't get hammered continuously if other keys are available.
            # But the base weight acts as gravity.
            score = key_data['weight'] 
            # Could implement more complex dynamic scoring based on `success`
            
            now = time.time()
            heapq.heappush(self._heap, (-score, now, key_data['id'], key_data))

    def report_error(self, key_data, error_type="429"):
        """
        Reports an error for a key. 
        It does NOT return the key to the local heap.
        It updates the DB status so other instances / future syncs know it's dead/cooling down.
        """
        key_value = key_data['key_value']
        provider = key_data['provider']
        
        try:
            with DBSession() as db:
                db_key = db.query(ApiKey).filter_by(key_value=key_value).first()
                if not db_key:
                    return

                if error_type == "429":
                    db_key.status = 'RATE_LIMITED'
                    
                    if provider == 'nvidia':
                        # Servidores da Nvidia são instáveis, punição de apenas 10 segundos para forçar retentativa rápida
                        db_key.cooldown_until = (datetime.utcnow() + timedelta(seconds=10)).isoformat()
                        logger.warning(f"[KeyManager] Key {db_key.id} ({provider}) hit 429 Rate Limit. Cooldown: 10s (Forçando Nvidia).")
                    else:
                        # 5 minutes cooldown padrão para Gemini
                        db_key.cooldown_until = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
                        logger.warning(f"[KeyManager] Key {db_key.id} ({provider}) hit 429 Rate Limit. Cooldown: 5m.")
                        
                elif error_type == "401":
                    db_key.status = 'INVALID'
                    logger.error(f"[KeyManager] Key {db_key.id} ({provider}) hit 401 Unauthorized. Marked INVALID.")
                else:
                    # Other errors, just release it back to the pool
                    self.release_key(key_data, success=False)
                    return

                db.commit()
        except Exception as e:
            logger.error(f"[KeyManager] Failed to report error to DB: {e}")
