<template>
  <div class="tts-settings">
    <!-- Loading State -->
    <div v-if="loading" class="tts-loading">
      <div class="tts-spinner"></div>
      <p>Loading TTS settings...</p>
    </div>

    <template v-else>
      <!-- General TTS Settings -->
      <div class="tts-section">
        <div class="tts-section-header" @click="toggleSection('general')">
          <div class="tts-section-title">
            <span class="tts-section-icon">🔊</span>
            <span>General TTS Settings</span>
          </div>
          <span class="tts-section-chevron" :class="{ expanded: expandedSections.general }">▼</span>
        </div>
        
        <div v-if="expandedSections.general" class="tts-section-content">
          <div class="tts-toggle-row">
            <label class="tts-toggle">
              <input v-model="config.enabled" type="checkbox" />
              <span class="tts-toggle-slider"></span>
            </label>
            <span class="tts-toggle-label">Enable TTS Alerts</span>
          </div>

          <div class="tts-form-group">
            <label class="tts-label">Media Player <span class="tts-required">*</span></label>
            <select v-model="config.media_player" class="tts-select">
              <option value="">-- Select Media Player --</option>
              <option v-for="mp in mediaPlayers" :key="mp.entity_id" :value="mp.entity_id">
                {{ mp.friendly_name }} ({{ mp.state }})
              </option>
            </select>
            <p v-if="!isAddon" class="tts-hint tts-hint-warning">
              ⚠️ Not running as HA addon. Enter media player entity ID manually.
            </p>
            <input
              v-if="!isAddon || mediaPlayers.length === 0"
              v-model="config.media_player"
              type="text"
              class="tts-input"
              placeholder="media_player.living_room"
            />
          </div>

          <div class="tts-form-group">
            <label class="tts-label">TTS Service <span class="tts-required">*</span></label>
            <select v-model="config.tts_service" class="tts-select">
              <option value="">-- Select TTS Service --</option>
              <option v-for="tts in ttsEntities" :key="tts.entity_id" :value="tts.entity_id">
                {{ tts.friendly_name }}
              </option>
              <option value="tts.google_translate_say">tts.google_translate_say</option>
              <option value="tts.cloud_say">tts.cloud_say</option>
              <option value="tts.piper">tts.piper</option>
            </select>
            <input
              v-if="!isAddon || ttsEntities.length === 0"
              v-model="config.tts_service"
              type="text"
              class="tts-input"
              placeholder="tts.google_translate_say"
            />
          </div>

          <div class="tts-form-group">
            <label class="tts-label">Volume</label>
            <div class="tts-volume-row">
              <input
                v-model.number="config.volume"
                type="range"
                class="tts-volume-slider"
                min="0"
                max="1"
                step="0.05"
              />
              <span class="tts-volume-value">{{ Math.round((config.volume || 0) * 100) }}%</span>
            </div>
          </div>

          <div class="tts-form-group">
            <label class="tts-label">Language</label>
            <input
              v-model="config.language"
              type="text"
              class="tts-input"
              placeholder="en, en-US"
            />
          </div>

          <div class="tts-toggle-row">
            <label class="tts-toggle">
              <input v-model="config.wait_for_idle" type="checkbox" />
              <span class="tts-toggle-slider"></span>
            </label>
            <span class="tts-toggle-label">Wait for media player idle</span>
          </div>
          <p class="tts-hint">Only play when media player is idle; otherwise wait up to 5 minutes</p>

          <button class="tts-btn tts-btn-primary" :disabled="saving" @click="saveConfig">
            {{ saving ? 'Saving...' : 'Save Settings' }}
          </button>

          <div v-if="generalMessage" :class="['tts-message', generalMessage.type]">
            {{ generalMessage.text }}
          </div>
        </div>
      </div>

      <!-- Scheduled TTS -->
      <div class="tts-section">
        <div class="tts-section-header" @click="toggleSection('schedule')">
          <div class="tts-section-title">
            <span class="tts-section-icon">⏰</span>
            <span>Scheduled Announcements</span>
          </div>
          <span class="tts-section-sub">Bill summary at scheduled times</span>
          <span class="tts-section-chevron" :class="{ expanded: expandedSections.schedule }">▼</span>
        </div>
        
        <div v-if="expandedSections.schedule" class="tts-section-content">
          <div class="tts-toggle-row">
            <label class="tts-toggle">
              <input v-model="schedule.enabled" type="checkbox" />
              <span class="tts-toggle-slider"></span>
            </label>
            <span class="tts-toggle-label">Enable Scheduled TTS</span>
          </div>

          <template v-if="schedule.enabled">
            <div class="tts-form-group">
              <label class="tts-label">Announce Every</label>
              <select v-model.number="schedule.hour_pattern" class="tts-select">
                <option :value="1">1 hour</option>
                <option :value="2">2 hours</option>
                <option :value="3">3 hours</option>
                <option :value="4">4 hours</option>
                <option :value="6">6 hours</option>
                <option :value="12">12 hours</option>
              </select>
            </div>

            <div class="tts-form-group">
              <label class="tts-label">Minute Offset (0-59)</label>
              <input
                v-model.number="schedule.minute_offset"
                type="number"
                class="tts-input"
                min="0"
                max="59"
              />
              <p class="tts-hint">e.g., 3 means announcements at :03 past the hour</p>
            </div>

            <div class="tts-form-group">
              <label class="tts-label">Active Hours</label>
              <div class="tts-time-row">
                <input v-model="schedule.start_time" type="time" class="tts-time-input" />
                <span class="tts-time-separator">to</span>
                <input v-model="schedule.end_time" type="time" class="tts-time-input" />
              </div>
            </div>

            <div class="tts-form-group">
              <label class="tts-label">Active Days</label>
              <div class="tts-days-row">
                <label
                  v-for="day in dayOptions"
                  :key="day.value"
                  class="tts-day-chip"
                  :class="{ active: schedule.days_of_week?.includes(day.value) }"
                >
                  <input
                    type="checkbox"
                    :checked="schedule.days_of_week?.includes(day.value)"
                    @change="toggleDay(day.value)"
                  />
                  {{ day.label }}
                </label>
              </div>
            </div>
          </template>

          <div class="tts-form-group">
            <label class="tts-label">Message Prefix</label>
            <input
              v-model="config.prefix"
              type="text"
              class="tts-input"
              placeholder="Message from Con Edison."
            />
            <p class="tts-hint">Prepended to every TTS message</p>
          </div>

          <div class="tts-actions-row">
            <button class="tts-btn tts-btn-primary" :disabled="scheduleSaving" @click="saveSchedule">
              {{ scheduleSaving ? 'Saving...' : 'Save Schedule' }}
            </button>
            <button
              class="tts-btn tts-btn-secondary"
              :disabled="!config.enabled || !config.media_player"
              @click="testBillSummary"
            >
              {{ testingSummary ? 'Sending...' : 'Test Bill Summary' }}
            </button>
          </div>

          <div v-if="scheduleMessage" :class="['tts-message', scheduleMessage.type]">
            {{ scheduleMessage.text }}
          </div>
        </div>
      </div>

      <!-- Message Preview -->
      <div class="tts-section">
        <div class="tts-section-header" @click="toggleSection('preview')">
          <div class="tts-section-title">
            <span class="tts-section-icon">👁️</span>
            <span>Message Preview</span>
          </div>
          <span class="tts-section-sub">See what TTS will say</span>
          <span class="tts-section-chevron" :class="{ expanded: expandedSections.preview }">▼</span>
        </div>
        
        <div v-if="expandedSections.preview" class="tts-section-content">
          <button class="tts-btn tts-btn-secondary" :disabled="loadingPreview" @click="loadPreview">
            {{ loadingPreview ? 'Generating...' : 'Generate Preview' }}
          </button>

          <div v-if="previewMessage" class="tts-preview-box">
            <div class="tts-preview-label">TTS Message:</div>
            <div class="tts-preview-text">{{ previewMessage }}</div>
          </div>

          <div v-if="previewData" class="tts-preview-data">
            <div class="tts-preview-item">
              <span class="tts-preview-key">Greeting:</span>
              <span>{{ previewData.greeting }}</span>
            </div>
            <div class="tts-preview-item">
              <span class="tts-preview-key">Time:</span>
              <span>{{ previewData.time }}</span>
            </div>
            <div class="tts-preview-item">
              <span class="tts-preview-key">Balance:</span>
              <span>{{ previewData.balance ?? 'N/A' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Message Templates -->
      <div class="tts-section">
        <div class="tts-section-header" @click="toggleSection('templates')">
          <div class="tts-section-title">
            <span class="tts-section-icon">📝</span>
            <span>Message Templates</span>
          </div>
          <span class="tts-section-sub">Customize event messages</span>
          <span class="tts-section-chevron" :class="{ expanded: expandedSections.templates }">▼</span>
        </div>
        
        <div v-if="expandedSections.templates" class="tts-section-content">
          <p class="tts-hint">
            Use <code>{placeholder}</code> for variables:
            <code>{amount}</code>, <code>{balance}</code>, <code>{month_range}</code>
          </p>

          <div v-for="(template, key) in config.messages" :key="key" class="tts-form-group">
            <label class="tts-label">{{ formatLabel(key) }}</label>
            <input
              v-model="config.messages[key]"
              type="text"
              class="tts-input"
              :placeholder="defaultMessages[key]"
            />
          </div>

          <button class="tts-btn tts-btn-primary" :disabled="saving" @click="saveConfig">
            {{ saving ? 'Saving...' : 'Save Templates' }}
          </button>
        </div>
      </div>

      <!-- Test TTS -->
      <div class="tts-section">
        <div class="tts-section-header" @click="toggleSection('test')">
          <div class="tts-section-title">
            <span class="tts-section-icon">🧪</span>
            <span>Test TTS</span>
          </div>
          <span class="tts-section-chevron" :class="{ expanded: expandedSections.test }">▼</span>
        </div>
        
        <div v-if="expandedSections.test" class="tts-section-content">
          <p class="tts-hint">Send a test message to verify your TTS configuration.</p>
          
          <button
            class="tts-btn tts-btn-orange"
            :disabled="!config.enabled || !config.media_player || testing"
            @click="testTts"
          >
            {{ testing ? 'Sending...' : 'Send Test TTS' }}
          </button>

          <div v-if="testMessage" :class="['tts-message', testMessage.type]">
            {{ testMessage.text }}
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { getApiBase } from '../../lib/api-base'

interface HaEntity {
  entity_id: string
  friendly_name: string
  state?: string
}

interface TtsConfig {
  enabled: boolean
  media_player: string
  volume: number
  language: string
  tts_service: string
  prefix: string
  wait_for_idle: boolean
  messages: Record<string, string>
}

interface Schedule {
  enabled: boolean
  hour_pattern: number
  minute_offset: number
  start_time: string
  end_time: string
  days_of_week: string[]
}

const loading = ref(true)
const saving = ref(false)
const scheduleSaving = ref(false)
const testing = ref(false)
const testingSummary = ref(false)
const loadingPreview = ref(false)

const isAddon = ref(false)
const mediaPlayers = ref<HaEntity[]>([])
const ttsEntities = ref<HaEntity[]>([])

const config = reactive<TtsConfig>({
  enabled: false,
  media_player: '',
  volume: 0.7,
  language: 'en',
  tts_service: 'tts.google_translate_say',
  prefix: 'Message from Con Edison.',
  wait_for_idle: true,
  messages: {
    new_bill: 'Your new Con Edison bill for {month_range} is now available.',
    payment_received: 'Good news — your payment of {amount} has been received. Your account balance is now {balance}.',
  }
})

const schedule = reactive<Schedule>({
  enabled: false,
  hour_pattern: 3,
  minute_offset: 0,
  start_time: '08:00',
  end_time: '21:00',
  days_of_week: ['mon', 'tue', 'wed', 'thu', 'fri']
})

const expandedSections = reactive({
  general: true,
  schedule: false,
  preview: false,
  templates: false,
  test: false
})

const generalMessage = ref<{ type: string; text: string } | null>(null)
const scheduleMessage = ref<{ type: string; text: string } | null>(null)
const testMessage = ref<{ type: string; text: string } | null>(null)
const previewMessage = ref('')
const previewData = ref<any>(null)

const dayOptions = [
  { value: 'mon', label: 'Mon' },
  { value: 'tue', label: 'Tue' },
  { value: 'wed', label: 'Wed' },
  { value: 'thu', label: 'Thu' },
  { value: 'fri', label: 'Fri' },
  { value: 'sat', label: 'Sat' },
  { value: 'sun', label: 'Sun' }
]

const defaultMessages: Record<string, string> = {
  new_bill: 'Your new Con Edison bill for {month_range} is now available.',
  payment_received: 'Good news — your payment of {amount} has been received. Your account balance is now {balance}.',
}

function toggleSection(key: keyof typeof expandedSections) {
  expandedSections[key] = !expandedSections[key]
}

function toggleDay(day: string) {
  if (!schedule.days_of_week) schedule.days_of_week = []
  const idx = schedule.days_of_week.indexOf(day)
  if (idx >= 0) {
    schedule.days_of_week.splice(idx, 1)
  } else {
    schedule.days_of_week.push(day)
  }
}

function formatLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

async function loadHaEntities() {
  try {
    const res = await fetch(`${getApiBase()}/ha-entities`)
    if (res.ok) {
      const data = await res.json()
      isAddon.value = data.is_addon || false
      mediaPlayers.value = data.media_players || []
      ttsEntities.value = data.tts_entities || []
    }
  } catch (e) {
    console.error('Failed to load HA entities:', e)
  }
}

async function loadConfig() {
  try {
    const res = await fetch(`${getApiBase()}/tts-config`)
    if (res.ok) {
      const data = await res.json()
      config.enabled = data.enabled ?? false
      config.media_player = data.media_player ?? ''
      config.volume = typeof data.volume === 'number' ? data.volume : 0.7
      config.language = data.language ?? 'en'
      config.tts_service = data.tts_service ?? 'tts.google_translate_say'
      config.prefix = data.prefix ?? 'Message from Con Edison.'
      config.wait_for_idle = data.wait_for_idle ?? true
      if (data.messages && typeof data.messages === 'object') {
        config.messages = { ...defaultMessages, ...data.messages }
      }
    }
  } catch (e) {
    console.error('Failed to load TTS config:', e)
  }
}

async function loadSchedule() {
  try {
    const res = await fetch(`${getApiBase()}/tts-schedule`)
    if (res.ok) {
      const data = await res.json()
      schedule.enabled = data.enabled ?? false
      schedule.hour_pattern = data.hour_pattern ?? 3
      schedule.minute_offset = data.minute_offset ?? 0
      schedule.start_time = data.start_time ?? '08:00'
      schedule.end_time = data.end_time ?? '21:00'
      schedule.days_of_week = data.days_of_week ?? ['mon', 'tue', 'wed', 'thu', 'fri']
    }
  } catch (e) {
    console.error('Failed to load schedule:', e)
  }
}

async function saveConfig() {
  saving.value = true
  generalMessage.value = null
  try {
    const res = await fetch(`${getApiBase()}/tts-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: config.enabled,
        media_player: config.media_player.trim(),
        volume: config.volume,
        language: config.language,
        prefix: config.prefix,
        tts_service: config.tts_service || 'tts.google_translate_say',
        wait_for_idle: config.wait_for_idle,
        messages: config.messages
      })
    })
    if (res.ok) {
      generalMessage.value = { type: 'success', text: 'TTS settings saved' }
    } else {
      const err = await res.json().catch(() => ({}))
      generalMessage.value = { type: 'error', text: err.detail || 'Failed to save' }
    }
  } catch {
    generalMessage.value = { type: 'error', text: 'Failed to connect' }
  } finally {
    saving.value = false
  }
}

async function saveSchedule() {
  scheduleSaving.value = true
  scheduleMessage.value = null
  try {
    const res = await fetch(`${getApiBase()}/tts-schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: schedule.enabled,
        hour_pattern: schedule.hour_pattern,
        minute_offset: schedule.minute_offset,
        start_time: schedule.start_time,
        end_time: schedule.end_time,
        days_of_week: schedule.days_of_week
      })
    })
    if (res.ok) {
      scheduleMessage.value = { type: 'success', text: 'Schedule saved' }
    } else {
      const err = await res.json().catch(() => ({}))
      scheduleMessage.value = { type: 'error', text: err.detail || 'Failed to save' }
    }
  } catch {
    scheduleMessage.value = { type: 'error', text: 'Failed to connect' }
  } finally {
    scheduleSaving.value = false
  }
}

async function testTts() {
  testing.value = true
  testMessage.value = null
  try {
    const res = await fetch(`${getApiBase()}/tts/test`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      testMessage.value = { type: 'success', text: data.message || 'TTS sent' }
    } else {
      testMessage.value = { type: 'error', text: data.detail || 'Failed' }
    }
  } catch {
    testMessage.value = { type: 'error', text: 'Failed to connect' }
  } finally {
    testing.value = false
  }
}

async function testBillSummary() {
  testingSummary.value = true
  scheduleMessage.value = null
  try {
    const res = await fetch(`${getApiBase()}/tts/trigger-bill-summary`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      scheduleMessage.value = { type: 'success', text: data.message || 'Bill summary sent' }
    } else {
      scheduleMessage.value = { type: 'error', text: data.detail || 'Failed' }
    }
  } catch {
    scheduleMessage.value = { type: 'error', text: 'Failed to connect' }
  } finally {
    testingSummary.value = false
  }
}

async function loadPreview() {
  loadingPreview.value = true
  previewMessage.value = ''
  previewData.value = null
  try {
    const res = await fetch(`${getApiBase()}/tts/preview-message`)
    if (res.ok) {
      const data = await res.json()
      previewMessage.value = data.message || ''
      previewData.value = data
    }
  } catch (e) {
    console.error('Failed to load preview:', e)
  } finally {
    loadingPreview.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadHaEntities(), loadConfig(), loadSchedule()])
  loading.value = false
})
</script>

<style scoped>
.tts-settings {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.tts-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: #888;
}

.tts-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e0e0e0;
  border-top-color: #ff9800;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.tts-section {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.tts-section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  cursor: pointer;
  background: #fafafa;
  border-bottom: 1px solid #eee;
  transition: background 0.2s;
}

.tts-section-header:hover {
  background: #f5f5f5;
}

.tts-section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: #333;
}

.tts-section-icon {
  font-size: 1.1rem;
}

.tts-section-sub {
  flex: 1;
  font-size: 0.85rem;
  color: #888;
  margin-left: 0.5rem;
}

.tts-section-chevron {
  color: #999;
  font-size: 0.75rem;
  transition: transform 0.2s;
}

.tts-section-chevron.expanded {
  transform: rotate(180deg);
}

.tts-section-content {
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.tts-form-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.tts-label {
  font-weight: 500;
  color: #444;
  font-size: 0.9rem;
}

.tts-required {
  color: #e65100;
}

.tts-input,
.tts-select {
  padding: 0.65rem 0.85rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 0.95rem;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.tts-input:focus,
.tts-select:focus {
  outline: none;
  border-color: #ff9800;
  box-shadow: 0 0 0 3px rgba(255, 152, 0, 0.1);
}

.tts-select {
  cursor: pointer;
}

.tts-hint {
  font-size: 0.8rem;
  color: #888;
  margin-top: 0.25rem;
}

.tts-hint code {
  background: #f0f0f0;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.8rem;
}

.tts-hint-warning {
  color: #f57c00;
}

.tts-toggle-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tts-toggle {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 26px;
}

.tts-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.tts-toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #ccc;
  border-radius: 26px;
  transition: background 0.3s;
}

.tts-toggle-slider::before {
  content: '';
  position: absolute;
  width: 22px;
  height: 22px;
  left: 2px;
  top: 2px;
  background: white;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transition: transform 0.3s;
}

.tts-toggle input:checked + .tts-toggle-slider {
  background: #ff9800;
}

.tts-toggle input:checked + .tts-toggle-slider::before {
  transform: translateX(22px);
}

.tts-toggle-label {
  font-weight: 500;
  color: #333;
}

.tts-volume-row {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.tts-volume-slider {
  flex: 1;
  height: 8px;
  -webkit-appearance: none;
  appearance: none;
  background: #e0e0e0;
  border-radius: 4px;
}

.tts-volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  background: #ff9800;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.tts-volume-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  background: #ff9800;
  border-radius: 50%;
  cursor: pointer;
  border: none;
}

.tts-volume-value {
  min-width: 3.5rem;
  font-weight: 500;
  color: #333;
}

.tts-time-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tts-time-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 0.95rem;
}

.tts-time-separator {
  color: #888;
}

.tts-days-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tts-day-chip {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.4rem 0.75rem;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.2s;
}

.tts-day-chip input {
  display: none;
}

.tts-day-chip.active {
  background: #ff9800;
  border-color: #ff9800;
  color: white;
}

.tts-actions-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.tts-btn {
  padding: 0.65rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.tts-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tts-btn-primary {
  background: #03a9f4;
  color: white;
}

.tts-btn-primary:hover:not(:disabled) {
  background: #0288d1;
}

.tts-btn-secondary {
  background: #e0e0e0;
  color: #333;
}

.tts-btn-secondary:hover:not(:disabled) {
  background: #d0d0d0;
}

.tts-btn-orange {
  background: #ff9800;
  color: white;
}

.tts-btn-orange:hover:not(:disabled) {
  background: #f57c00;
}

.tts-message {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
}

.tts-message.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.tts-message.error {
  background: #ffebee;
  color: #c62828;
}

.tts-preview-box {
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 1rem;
}

.tts-preview-label {
  font-weight: 600;
  color: #666;
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.tts-preview-text {
  font-size: 1rem;
  color: #333;
  line-height: 1.6;
  font-style: italic;
}

.tts-preview-data {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: #fafafa;
  border-radius: 8px;
}

.tts-preview-item {
  display: flex;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.tts-preview-key {
  font-weight: 600;
  color: #666;
}
</style>
