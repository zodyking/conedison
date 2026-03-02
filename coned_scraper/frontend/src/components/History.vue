<template>
  <div class="ha-history">
    <!-- Loading -->
    <div v-if="isLoading" class="ha-loading-state">
      <div class="ha-loading-spinner"></div>
      <div class="ha-loading-text">Loading billing history...</div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="ha-error-state">{{ error }}</div>

    <!-- No Data -->
    <div v-else-if="!historyData.length" class="ha-empty-data">
      <div class="ha-empty-icon">📊</div>
      <h2 class="ha-empty-title">No History Data Yet</h2>
      <p class="ha-empty-desc">
        Upload bill PDFs in Settings to populate billing history charts.
      </p>
    </div>

    <!-- History Content -->
    <div v-else class="ha-history-content">
      <!-- Summary Cards -->
      <div class="ha-history-summary">
        <div class="ha-summary-card">
          <div class="ha-summary-card-icon">⚡</div>
          <div class="ha-summary-card-content">
            <div class="ha-summary-card-label">Avg. kWh/Month</div>
            <div class="ha-summary-card-value">{{ averageKwh }}</div>
          </div>
        </div>
        <div class="ha-summary-card">
          <div class="ha-summary-card-icon">💵</div>
          <div class="ha-summary-card-content">
            <div class="ha-summary-card-label">Avg. kWh Cost</div>
            <div class="ha-summary-card-value">${{ averageKwhCost }}/kWh</div>
          </div>
        </div>
        <div class="ha-summary-card">
          <div class="ha-summary-card-icon">📈</div>
          <div class="ha-summary-card-content">
            <div class="ha-summary-card-label">Avg. Bill</div>
            <div class="ha-summary-card-value">${{ averageBill }}</div>
          </div>
        </div>
        <div class="ha-summary-card">
          <div class="ha-summary-card-icon">📅</div>
          <div class="ha-summary-card-content">
            <div class="ha-summary-card-label">Bills Tracked</div>
            <div class="ha-summary-card-value">{{ historyData.length }}</div>
          </div>
        </div>
      </div>

      <!-- kWh Usage Chart -->
      <div class="ha-chart-card">
        <div class="ha-chart-header">
          <span class="ha-chart-icon">⚡</span>
          <span>kWh Usage Over Time</span>
        </div>
        <div class="ha-chart-container">
          <canvas ref="kwhChart"></canvas>
        </div>
      </div>

      <!-- Bill Total Chart -->
      <div class="ha-chart-card">
        <div class="ha-chart-header">
          <span class="ha-chart-icon">💰</span>
          <span>Bill Totals Over Time</span>
        </div>
        <div class="ha-chart-container">
          <canvas ref="billChart"></canvas>
        </div>
      </div>

      <!-- kWh Cost Chart -->
      <div class="ha-chart-card">
        <div class="ha-chart-header">
          <span class="ha-chart-icon">📊</span>
          <span>Cost per kWh Over Time</span>
        </div>
        <div class="ha-chart-container">
          <canvas ref="kwhCostChart"></canvas>
        </div>
      </div>

      <!-- Supply vs Delivery Rates ($/kWh) -->
      <div class="ha-chart-card">
        <div class="ha-chart-header">
          <span class="ha-chart-icon">🔌</span>
          <span>Supply vs Delivery Rates ($/kWh)</span>
        </div>
        <div class="ha-chart-container">
          <canvas ref="supplyDeliveryChart"></canvas>
        </div>
      </div>

      <!-- Detailed History Table -->
      <div class="ha-chart-card">
        <div class="ha-chart-header">
          <span class="ha-chart-icon">📋</span>
          <span>Detailed Billing History</span>
        </div>
        <div class="ha-table-container">
          <table class="ha-history-table">
            <thead>
              <tr>
                <th>Bill Cycle</th>
                <th>kWh</th>
                <th>$/kWh</th>
                <th>Supply</th>
                <th>Supply Rate</th>
                <th>Delivery</th>
                <th>Delivery Rate</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in historyData" :key="row.bill_id">
                <td>{{ formatBillCycleDate(row.bill_cycle_date) }}</td>
                <td>{{ formatNumber(row.kwh_used) }}</td>
                <td>{{ row.kwh_cost ? `$${row.kwh_cost.toFixed(4)}` : '—' }}</td>
                <td>{{ row.supply_total ? `$${row.supply_total.toFixed(2)}` : '—' }}</td>
                <td>{{ row.supply_rate ? `$${row.supply_rate.toFixed(4)}` : '—' }}</td>
                <td>{{ row.delivery_total ? `$${row.delivery_total.toFixed(2)}` : '—' }}</td>
                <td>{{ row.delivery_rate ? `$${row.delivery_rate.toFixed(4)}` : '—' }}</td>
                <td class="ha-total-cell">{{ row.electricity_total ? `$${row.electricity_total.toFixed(2)}` : (row.bill_total || '—') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { getApiBase } from '../lib/api-base'
import {
  Chart,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  BarController,
  LineController,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'

Chart.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  BarController,
  LineController,
  Title,
  Tooltip,
  Legend,
  Filler
)

interface HistoryRow {
  bill_id: number
  month_range: string | null
  bill_cycle_date: string | null
  bill_total: string | null
  amount_numeric: number | null
  kwh_used: number | null
  kwh_cost: number | null
  electricity_total: number | null
  total_from_billing_period: number | null
  balance_from_previous_bill: number
  billing_days: number | null
  supply_total: number
  supply_rate: number
  delivery_total: number
  delivery_rate: number
}

const isLoading = ref(true)
const error = ref<string | null>(null)
const historyData = ref<HistoryRow[]>([])

const kwhChart = ref<HTMLCanvasElement | null>(null)
const billChart = ref<HTMLCanvasElement | null>(null)
const kwhCostChart = ref<HTMLCanvasElement | null>(null)
const supplyDeliveryChart = ref<HTMLCanvasElement | null>(null)

let chartInstances: Chart[] = []

const averageKwh = computed(() => {
  const vals = historyData.value.filter(r => r.kwh_used).map(r => r.kwh_used!)
  if (!vals.length) return '—'
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length).toLocaleString()
})

const averageKwhCost = computed(() => {
  const vals = historyData.value.filter(r => r.kwh_cost).map(r => r.kwh_cost!)
  if (!vals.length) return '—'
  return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(4)
})

const averageBill = computed(() => {
  const vals = historyData.value
    .filter(r => r.electricity_total || r.amount_numeric)
    .map(r => r.electricity_total || r.amount_numeric || 0)
  if (!vals.length) return '—'
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length).toLocaleString()
})


function formatNumber(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString()
}

function formatBillCycleDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  try {
    // Handle M/D/YYYY or MM/DD/YYYY format
    const parts = dateStr.split('/')
    if (parts.length === 3) {
      const month = parseInt(parts[0], 10)
      const day = parseInt(parts[1], 10)
      const year = parseInt(parts[2], 10)
      const date = new Date(year, month - 1, day)
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }
    // Fallback for other formats
    const date = new Date(dateStr)
    if (!isNaN(date.getTime())) {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }
    return dateStr
  } catch {
    return dateStr
  }
}

async function fetchHistory() {
  isLoading.value = true
  error.value = null
  try {
    // Use same endpoint as AccountLedger to ensure consistent data/ordering
    const res = await fetch(`${getApiBase()}/ledger`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const ledger = await res.json()
    const bills = ledger.bills || []
    
    // Also fetch bill details for the extra parsed data (kwh, supply/delivery)
    const detailsRes = await fetch(`${getApiBase()}/bill-history`)
    let detailsMap: Record<number, any> = {}
    if (detailsRes.ok) {
      const detailsData = await detailsRes.json()
      for (const d of (detailsData.history || [])) {
        detailsMap[d.bill_id] = d
      }
    }
    
    // Merge ledger bills with details - bills are already in correct order from ledger
    historyData.value = bills.map((bill: any) => {
      const details = detailsMap[bill.id] || {}
      return {
        bill_id: bill.id,
        month_range: bill.month_range,
        bill_cycle_date: bill.bill_cycle_date,
        bill_total: bill.bill_total,
        amount_numeric: bill.amount_numeric,
        kwh_used: details.kwh_used || null,
        kwh_cost: details.kwh_cost || null,
        electricity_total: details.electricity_total || null,
        total_from_billing_period: details.total_from_billing_period || null,
        balance_from_previous_bill: details.balance_from_previous_bill || 0,
        billing_days: details.billing_days || null,
        supply_total: details.supply_total || 0,
        supply_rate: details.supply_rate || 0,
        delivery_total: details.delivery_total || 0,
        delivery_rate: details.delivery_rate || 0,
      }
    })
  } catch (e: any) {
    error.value = e.message || 'Failed to load history'
  } finally {
    isLoading.value = false
  }
}

function destroyCharts() {
  chartInstances.forEach(c => c.destroy())
  chartInstances = []
}

function createCharts() {
  destroyCharts()
  
  // For charts, use chronological order (oldest first) - reverse the DESC order from ledger
  const chartData = [...historyData.value].reverse()
  const labels = chartData.map(r => r.month_range || `Bill ${r.bill_id}`)
  
  // kWh Usage Chart
  if (kwhChart.value) {
    const ctx = kwhChart.value.getContext('2d')
    if (ctx) {
      chartInstances.push(new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'kWh Used',
            data: chartData.map(r => r.kwh_used || 0),
            backgroundColor: 'rgba(0, 136, 204, 0.7)',
            borderColor: 'rgba(0, 136, 204, 1)',
            borderWidth: 1,
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.parsed.y.toLocaleString()} kWh`
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              title: { display: true, text: 'kWh' }
            }
          }
        }
      }))
    }
  }

  // Bill Total Chart - Stacked bar with current period + previous balance
  if (billChart.value) {
    const ctx = billChart.value.getContext('2d')
    if (ctx) {
      chartInstances.push(new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'Current Cycle',
              data: chartData.map(r => r.total_from_billing_period || r.electricity_total || r.amount_numeric || 0),
              backgroundColor: 'rgba(34, 139, 34, 0.7)',
              borderColor: 'rgba(34, 139, 34, 1)',
              borderWidth: 1,
              borderRadius: 4
            },
            {
              label: 'Previous Balance',
              data: chartData.map(r => r.balance_from_previous_bill || 0),
              backgroundColor: 'rgba(255, 99, 132, 0.7)',
              borderColor: 'rgba(255, 99, 132, 1)',
              borderWidth: 1,
              borderRadius: 4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'top' },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              stacked: true,
              title: { display: true, text: 'USD ($)' }
            },
            x: {
              stacked: true
            }
          }
        }
      }))
    }
  }

  // kWh Cost Chart
  if (kwhCostChart.value) {
    const ctx = kwhCostChart.value.getContext('2d')
    if (ctx) {
      chartInstances.push(new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: '$/kWh',
            data: chartData.map(r => r.kwh_cost || 0),
            borderColor: 'rgba(220, 20, 60, 1)',
            backgroundColor: 'rgba(220, 20, 60, 0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 5,
            pointBackgroundColor: 'rgba(220, 20, 60, 1)'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `$${ctx.parsed.y.toFixed(4)}/kWh`
              }
            }
          },
          scales: {
            y: {
              beginAtZero: false,
              title: { display: true, text: '$/kWh' }
            }
          }
        }
      }))
    }
  }

  // Supply vs Delivery Rates Chart ($/kWh)
  if (supplyDeliveryChart.value) {
    const ctx = supplyDeliveryChart.value.getContext('2d')
    if (ctx) {
      chartInstances.push(new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'Supply Rate',
              data: chartData.map(r => r.supply_rate || 0),
              backgroundColor: 'rgba(255, 159, 64, 0.7)',
              borderColor: 'rgba(255, 159, 64, 1)',
              borderWidth: 1,
              borderRadius: 4
            },
            {
              label: 'Delivery Rate',
              data: chartData.map(r => r.delivery_rate || 0),
              backgroundColor: 'rgba(75, 192, 192, 0.7)',
              borderColor: 'rgba(75, 192, 192, 1)',
              borderWidth: 1,
              borderRadius: 4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'top' },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(4)}/kWh`
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              stacked: true,
              title: { display: true, text: '$/kWh' }
            },
            x: {
              stacked: true
            }
          }
        }
      }))
    }
  }
}

watch(historyData, async () => {
  await nextTick()
  if (historyData.value.length > 0) {
    createCharts()
  }
})

onMounted(async () => {
  await fetchHistory()
})

onUnmounted(() => {
  destroyCharts()
})
</script>

<style scoped>
.ha-history {
  padding: 16px;
}

.ha-loading-state,
.ha-error-state,
.ha-empty-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.ha-loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--ha-border-color, #e0e0e0);
  border-top-color: var(--ha-primary-color, #0088cc);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.ha-loading-text {
  margin-top: 12px;
  color: var(--ha-secondary-text-color, #666);
  font-size: 14px;
}

.ha-error-state {
  color: var(--ha-error-color, #dc3545);
  font-size: 14px;
}

.ha-empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.ha-empty-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--ha-primary-text-color, #333);
}

.ha-empty-desc {
  margin: 0;
  color: var(--ha-secondary-text-color, #666);
  font-size: 14px;
  max-width: 300px;
}

.ha-history-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ha-history-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.ha-summary-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--ha-card-background, #fff);
  border: 1px solid var(--ha-border-color, #e0e0e0);
  border-radius: 8px;
}

.ha-summary-card-icon {
  font-size: 28px;
}

.ha-summary-card-content {
  flex: 1;
  min-width: 0;
}

.ha-summary-card-label {
  font-size: 12px;
  color: var(--ha-secondary-text-color, #666);
  margin-bottom: 4px;
}

.ha-summary-card-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--ha-primary-text-color, #333);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ha-chart-card {
  background: var(--ha-card-background, #fff);
  border: 1px solid var(--ha-border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.ha-chart-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--ha-card-header-bg, #f8f9fa);
  border-bottom: 1px solid var(--ha-border-color, #e0e0e0);
  font-weight: 600;
  font-size: 14px;
  color: var(--ha-primary-text-color, #333);
}

.ha-chart-icon {
  font-size: 16px;
}

.ha-chart-container {
  padding: 16px;
  height: 280px;
}

.ha-table-container {
  overflow-x: auto;
}

.ha-history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.ha-history-table th,
.ha-history-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--ha-border-color, #e0e0e0);
}

.ha-history-table th {
  background: var(--ha-card-header-bg, #f8f9fa);
  font-weight: 600;
  color: var(--ha-secondary-text-color, #666);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ha-history-table tbody tr:hover {
  background: var(--ha-hover-bg, #f5f5f5);
}

.ha-total-cell {
  font-weight: 600;
  color: var(--ha-primary-text-color, #333);
}

@media (max-width: 600px) {
  .ha-history-summary {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .ha-summary-card {
    padding: 12px;
  }
  
  .ha-summary-card-icon {
    font-size: 24px;
  }
  
  .ha-summary-card-value {
    font-size: 16px;
  }
  
  .ha-chart-container {
    height: 220px;
  }
  
  .ha-history-table {
    font-size: 12px;
  }
  
  .ha-history-table th,
  .ha-history-table td {
    padding: 8px 6px;
  }
}
</style>
