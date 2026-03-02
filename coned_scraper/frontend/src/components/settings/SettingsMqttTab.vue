<template>
  <div class="ha-card">
    <div class="ha-card-header">
      <span class="ha-card-icon">📡</span>
      <span>MQTT Configuration</span>
    </div>
    <div class="ha-card-content">
      <div class="info-text" style="margin-bottom: 1.5rem">
        Configure MQTT to publish sensor data to Home Assistant. With <strong>MQTT Discovery</strong> enabled, sensors like <code>sensor.ConEd_latest_bill</code> and <code>sensor.ConEd_account_balance</code> are auto-registered—no manual configuration.yaml needed.
      </div>
      <form @submit.prevent="handleSave">
        <div class="ha-form-group">
          <label for="mqtt-url" class="ha-form-label">MQTT Broker URL</label>
          <input id="mqtt-url" v-model="mqttUrl" type="text" class="ha-form-input ha-input-mono" placeholder="mqtt://homeassistant.local:1883" />
          <div class="info-text">Leave empty to disable MQTT publishing</div>
        </div>
        <div class="ha-form-group">
          <label for="mqtt-username" class="ha-form-label">MQTT Username</label>
          <input id="mqtt-username" v-model="mqttUsername" type="text" class="ha-form-input" placeholder="Optional" />
        </div>
        <div class="ha-form-group">
          <label for="mqtt-password" class="ha-form-label">MQTT Password <span class="hint">(leave empty to keep existing)</span></label>
          <input id="mqtt-password" v-model="mqttPassword" type="password" class="ha-form-input" placeholder="Optional" autocomplete="new-password" />
        </div>
        <div class="ha-form-group">
          <label for="mqtt-base-topic" class="ha-form-label">Base Topic</label>
          <input id="mqtt-base-topic" v-model="mqttBaseTopic" type="text" class="ha-form-input ha-input-mono" placeholder="coned" />
          <div class="info-text">Topics will be: {{ mqttBaseTopic || 'coned' }}/account_balance, etc.</div>
        </div>
        <div class="ha-form-group">
          <label for="mqtt-qos" class="ha-form-label">Quality of Service (QoS)</label>
          <select id="mqtt-qos" v-model.number="mqttQos" class="ha-form-input">
            <option :value="0">0 - At most once</option>
            <option :value="1">1 - At least once</option>
            <option :value="2">2 - Exactly once</option>
          </select>
        </div>
        <div class="ha-form-group">
          <label class="ha-check-label">
            <input v-model="mqttRetain" type="checkbox" />
            <span>Retain Messages</span>
          </label>
          <div class="info-text">Retained messages persist on the broker</div>
        </div>
        <div class="ha-form-group">
          <label class="ha-check-label">
            <input v-model="mqttDiscovery" type="checkbox" />
            <span>MQTT Discovery (auto-register sensors)</span>
          </label>
          <div class="info-text">Publish discovery configs so Home Assistant creates sensors (e.g. sensor.ConEd_latest_bill) automatically</div>
        </div>
        <button type="submit" class="ha-button ha-button-primary" :disabled="isLoading">{{ isLoading ? 'Saving...' : 'Save MQTT Config' }}</button>
      </form>
      <div v-if="message" :class="['ha-message', message.type]">{{ message.text }}</div>
      
      <!-- MQTT Cleanup Section -->
      <div class="ha-card-divider"></div>
      <div class="cleanup-section">
        <div class="cleanup-header">
          <span class="cleanup-icon">🧹</span>
          <span class="cleanup-title">Sensor Cleanup</span>
        </div>
        <div class="info-text" style="margin-bottom: 1rem">
          If you see duplicate sensors (e.g., <code>sensor.ConEd_account_balance_2</code>), use this to clear all retained MQTT discovery messages from the broker. After cleanup, restart the addon to re-register sensors cleanly.
        </div>
        <button 
          type="button" 
          class="ha-button ha-button-warning" 
          :disabled="isCleaningUp"
          @click="handleCleanup"
        >
          {{ isCleaningUp ? 'Cleaning up...' : 'Clear Duplicate Sensors' }}
        </button>
        <div v-if="cleanupMessage" :class="['ha-message', cleanupMessage.type]" style="margin-top: 0.75rem">
          {{ cleanupMessage.text }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApiBase } from '../../lib/api-base'

const mqttUrl = ref('')
const mqttUsername = ref('')
const mqttPassword = ref('')
const mqttBaseTopic = ref('coned')
const mqttQos = ref(1)
const mqttRetain = ref(true)
const mqttDiscovery = ref(true)
const isLoading = ref(false)
const isCleaningUp = ref(false)
const message = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const cleanupMessage = ref<{ type: 'success' | 'error'; text: string } | null>(null)

async function loadMqttConfig() {
  try {
    const res = await fetch(`${getApiBase()}/mqtt-config`)
    if (res.ok) {
      const data = await res.json()
      mqttUrl.value = data.mqtt_url || ''
      mqttUsername.value = data.mqtt_username || ''
      mqttPassword.value = ''
      mqttBaseTopic.value = data.mqtt_base_topic || 'coned'
      mqttQos.value = data.mqtt_qos ?? 1
      mqttRetain.value = data.mqtt_retain !== undefined ? data.mqtt_retain : true
      mqttDiscovery.value = data.mqtt_discovery !== undefined ? data.mqtt_discovery : true
    }
  } catch (e) {
    console.error(e)
  }
}

async function handleSave() {
  isLoading.value = true
  message.value = null
  try {
    const res = await fetch(`${getApiBase()}/mqtt-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mqtt_url: mqttUrl.value.trim(),
        mqtt_username: mqttUsername.value.trim(),
        mqtt_password: mqttPassword.value || undefined,
        mqtt_base_topic: mqttBaseTopic.value.trim() || 'coned',
        mqtt_qos: mqttQos.value,
        mqtt_retain: mqttRetain.value,
        mqtt_discovery: mqttDiscovery.value,
      }),
    })
    if (res.ok) {
      message.value = { type: 'success', text: 'MQTT configuration saved successfully!' }
      await loadMqttConfig()
    } else {
      const err = await res.json().catch(() => ({}))
      message.value = { type: 'error', text: err.detail || 'Failed to save MQTT config' }
    }
  } catch {
    message.value = { type: 'error', text: 'Failed to connect to API.' }
  } finally {
    isLoading.value = false
  }
}

async function handleCleanup() {
  isCleaningUp.value = true
  cleanupMessage.value = null
  try {
    const res = await fetch(`${getApiBase()}/mqtt-cleanup`, {
      method: 'POST',
    })
    if (res.ok) {
      cleanupMessage.value = { 
        type: 'success', 
        text: 'MQTT sensors cleared from broker. Please restart the addon to re-register sensors cleanly.' 
      }
    } else {
      const err = await res.json().catch(() => ({}))
      cleanupMessage.value = { type: 'error', text: err.detail || 'Failed to clean up MQTT sensors' }
    }
  } catch {
    cleanupMessage.value = { type: 'error', text: 'Failed to connect to API.' }
  } finally {
    isCleaningUp.value = false
  }
}

onMounted(loadMqttConfig)
</script>

<style scoped>
.ha-input-mono { font-family: monospace; font-size: 0.9rem; }
.hint { font-size: 0.85rem; font-weight: normal; margin-left: 0.5rem; color: #666; }
.ha-check-label { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }
code { font-family: monospace; font-size: 0.9em; background: #f0f0f0; padding: 0.1em 0.3em; border-radius: 3px; }
.ha-check-label input { width: 18px; height: 18px; }
.ha-message { margin-top: 1rem; padding: 0.75rem; border-radius: 4px; }
.ha-message.success { background: #e8f5e9; color: #2e7d32; }
.ha-message.error { background: #ffebee; color: #c62828; }
.ha-card-divider { border-top: 1px solid #e0e0e0; margin: 1.5rem 0; }
.cleanup-section { padding-top: 0.5rem; }
.cleanup-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.cleanup-icon { font-size: 1.25rem; }
.cleanup-title { font-weight: 600; font-size: 1rem; }
.ha-button-warning { 
  background: #ff9800; 
  color: white; 
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}
.ha-button-warning:hover { background: #f57c00; }
.ha-button-warning:disabled { background: #ffcc80; cursor: not-allowed; }
</style>
