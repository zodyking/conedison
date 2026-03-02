<template>
  <div class="ha-card">
    <div class="ha-card-header">
      <span class="ha-card-icon">⚡</span>
      <span>Meter Tracking</span>
    </div>
    <div class="ha-card-content">
      <div class="info-text" style="margin-bottom: 1rem">
        Connect to Con Edison's Opower API for near real-time meter readings using the 
        <a href="https://github.com/tronikos/opower" target="_blank" rel="noopener">opower</a> library 
        (same as Home Assistant's Opower integration). This creates MQTT sensors for current usage (kWh) and calculated cost.
      </div>
      
      <div class="ha-form-group">
        <label class="ha-check-label">
          <input v-model="config.enabled" type="checkbox" />
          <span>Enable Meter Tracking</span>
        </label>
      </div>

      <div class="ha-form-group">
        <label class="ha-form-label">Con Edison Email</label>
        <input v-model="config.email" type="email" class="ha-form-input" placeholder="your@email.com" />
      </div>

      <div class="ha-form-group">
        <label class="ha-form-label">Password</label>
        <input v-model="config.password" type="password" class="ha-form-input" placeholder="••••••••" />
      </div>

      <div class="ha-form-group">
        <label class="ha-form-label">TOTP Secret</label>
        <input v-model="config.totp_secret" type="password" class="ha-form-input" placeholder="Base32 TOTP secret from authenticator setup" />
        <div class="info-text">
          In ConEd settings, set up Google Authenticator. Click "Can't scan?" to get the secret key.
          <a href="https://github.com/tronikos/opower#supported-utilities" target="_blank" rel="noopener">More info</a>
        </div>
      </div>

      <div class="ha-form-group">
        <label class="ha-form-label">Polling Interval (minutes)</label>
        <input v-model.number="config.polling_interval" type="number" min="5" max="60" class="ha-form-input" />
        <div class="info-text">How often to fetch meter readings (minimum 5 minutes)</div>
      </div>

      <div class="ha-form-actions">
        <button type="button" class="ha-button ha-button-primary" :disabled="isLoading" @click="handleSave">
          {{ isLoading ? 'Saving...' : 'Save' }}
        </button>
        <button type="button" class="ha-button" :disabled="isLoading || !config.enabled" @click="handleTest">
          Test Connection
        </button>
        <button type="button" class="ha-button" :disabled="isLoading || !config.enabled" @click="handleRefresh">
          Refresh Reading
        </button>
      </div>

      <div v-if="message" :class="['ha-message', message.type]">{{ message.text }}</div>

      <div v-if="lastReading" class="ha-reading-info">
        <div class="ha-reading-header">Latest Reading</div>
        <div class="ha-reading-row">
          <span class="ha-reading-label">Usage:</span>
          <span class="ha-reading-value">{{ lastReading.value }} {{ lastReading.unit }}</span>
        </div>
        <div v-if="lastReadingCost !== null" class="ha-reading-row">
          <span class="ha-reading-label">Estimated Cost:</span>
          <span class="ha-reading-value">${{ lastReadingCost.toFixed(2) }}</span>
        </div>
        <div class="ha-reading-row">
          <span class="ha-reading-label">Fetched:</span>
          <span class="ha-reading-value ha-reading-time">{{ formatTime(lastReading.fetched_at) }}</span>
        </div>
      </div>

      <div class="mqtt-sensor-info">
        <div class="mqtt-sensor-header">MQTT Sensors Created</div>
        <ul class="mqtt-sensor-list">
          <li><code>sensor.coned_current_meter_usage</code> — Current meter reading (kWh)</li>
          <li><code>sensor.coned_current_usage_cost</code> — Calculated cost (USD)</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { getApiBase } from '../../lib/api-base'

interface MeterReading {
  start_time: string | null
  end_time: string | null
  value: number | null
  unit: string
  fetched_at: string
}

const config = reactive({
  enabled: false,
  email: '',
  password: '',
  totp_secret: '',
  polling_interval: 15
})

const isLoading = ref(false)
const message = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const lastReading = ref<MeterReading | null>(null)
const lastReadingCost = ref<number | null>(null)

function formatTime(isoString: string | null): string {
  if (!isoString) return '—'
  try {
    const date = new Date(isoString)
    return date.toLocaleString()
  } catch {
    return isoString
  }
}

async function loadConfig() {
  try {
    const res = await fetch(`${getApiBase()}/meter-config`)
    if (res.ok) {
      const d = await res.json()
      config.enabled = d.enabled || false
      config.email = d.email || ''
      config.password = d.password || ''
      config.totp_secret = d.totp_secret || ''
      config.polling_interval = d.polling_interval ?? 15
    }
  } catch (e) {
    console.error('Failed to load meter config:', e)
  }
}

async function loadReading() {
  try {
    const res = await fetch(`${getApiBase()}/meter-reading`)
    if (res.ok) {
      const d = await res.json()
      if (d.reading) {
        lastReading.value = d.reading
        lastReadingCost.value = d.cost ?? null
      }
    }
  } catch (e) {
    console.error('Failed to load meter reading:', e)
  }
}

async function handleSave() {
  isLoading.value = true
  message.value = null
  try {
    const res = await fetch(`${getApiBase()}/meter-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    })
    if (res.ok) {
      message.value = { type: 'success', text: 'Meter configuration saved!' }
      await loadReading()
    } else {
      const err = await res.json().catch(() => ({}))
      message.value = { type: 'error', text: err.detail || 'Failed to save' }
    }
  } catch {
    message.value = { type: 'error', text: 'Failed to connect' }
  } finally {
    isLoading.value = false
  }
}

async function handleTest() {
  isLoading.value = true
  message.value = null
  try {
    const res = await fetch(`${getApiBase()}/meter-config/test`, { method: 'POST' })
    const d = await res.json()
    if (d.success) {
      message.value = { type: 'success', text: d.message }
      if (d.reading) {
        lastReading.value = d.reading
      }
      await loadReading()
    } else {
      message.value = { type: 'error', text: d.detail || d.message || 'Test failed' }
    }
  } catch {
    message.value = { type: 'error', text: 'Connection test failed' }
  } finally {
    isLoading.value = false
  }
}

async function handleRefresh() {
  isLoading.value = true
  message.value = null
  try {
    const res = await fetch(`${getApiBase()}/meter-reading/refresh`, { method: 'POST' })
    const d = await res.json()
    if (d.success) {
      message.value = { type: 'success', text: `Reading updated: ${d.reading?.value ?? 0} kWh` }
      lastReading.value = d.reading
      lastReadingCost.value = d.cost ?? null
    } else {
      message.value = { type: 'error', text: d.detail || 'Failed to refresh' }
    }
  } catch {
    message.value = { type: 'error', text: 'Failed to refresh reading' }
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  loadConfig()
  loadReading()
})
</script>

<style scoped>
.ha-check-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}
.ha-check-label input {
  width: 18px;
  height: 18px;
}
.ha-form-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}
.ha-message {
  margin-top: 1rem;
  padding: 0.75rem;
  border-radius: 4px;
}
.ha-message.success {
  background: #e8f5e9;
  color: #2e7d32;
}
.ha-message.error {
  background: #ffebee;
  color: #c62828;
}
.ha-reading-info {
  margin-top: 1.5rem;
  padding: 1rem;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border-radius: 8px;
  border-left: 4px solid #1976d2;
}
.ha-reading-header {
  font-weight: 600;
  font-size: 0.9rem;
  color: #1565c0;
  margin-bottom: 0.75rem;
}
.ha-reading-row {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 0;
}
.ha-reading-label {
  color: #37474f;
  font-size: 0.9rem;
}
.ha-reading-value {
  font-weight: 600;
  color: #0d47a1;
}
.ha-reading-time {
  font-weight: 400;
  font-size: 0.85rem;
  color: #546e7a;
}
.mqtt-sensor-info {
  margin-top: 1.5rem;
  padding: 1rem;
  background: #f5f5f5;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}
.mqtt-sensor-header {
  font-weight: 600;
  font-size: 0.9rem;
  color: #424242;
  margin-bottom: 0.5rem;
}
.mqtt-sensor-list {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.85rem;
  color: #616161;
}
.mqtt-sensor-list li {
  margin: 0.25rem 0;
}
.mqtt-sensor-list code {
  background: #e0e0e0;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-family: monospace;
  font-size: 0.8rem;
}
</style>
