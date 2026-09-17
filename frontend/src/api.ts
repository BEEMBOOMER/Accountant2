import type { Account, Analytics, AnalyticsMonths, Category, ImportDetection, ImportResult, Rule, Transaction, TransactionClassification } from './types'

const api = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(`/api${path}`, { ...options, headers: { ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options?.headers } })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json() as { detail?: string; message?: string }; message = body.detail ?? body.message ?? message } catch { /* response may not be json */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const unwrap = <T,>(value: T | { data: T }): T => (value && typeof value === 'object' && 'data' in value ? (value as { data: T }).data : value as T)

export const client = {
  health: () => api<{ status: string }>('/health'),
  analytics: async (month: string) => unwrap(await api<Analytics | { data: Analytics }>(`/analytics?month=${encodeURIComponent(month)}`)),
  analyticsMonths: async () => unwrap(await api<AnalyticsMonths | { data: AnalyticsMonths }>('/analytics/months')),
  transactions: async (params: Record<string, string>) => {
    const response = await api<{ transactions: Transaction[]; total: number }>(`/transactions?${new URLSearchParams(params)}`)
    return response.transactions
  },
  accounts: async () => unwrap(await api<Account[] | { data: Account[] }>('/accounts')),
  createAccount: (body: Omit<Account, 'id'>) => api<Account>('/accounts', { method: 'POST', body: JSON.stringify(body) }),
  updateAccount: (id: string, body: Partial<Account>) => api<Account>(`/accounts/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAccount: (id: string) => api<void>(`/accounts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  categories: async () => unwrap(await api<Category[] | { data: Category[] }>('/categories')),
  createCategory: (name: string) => api<Category>('/categories', { method: 'POST', body: JSON.stringify({ name }) }),
  updateCategory: (id: string, name: string) => api<Category>(`/categories/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteCategory: (id: string, replacement_category_id: string) => api<void>(`/categories/${encodeURIComponent(id)}?replacement_category_id=${encodeURIComponent(replacement_category_id)}`, { method: 'DELETE' }),
  rules: async () => unwrap(await api<Rule[] | { data: Rule[] }>('/rules')),
  createRule: (body: Omit<Rule, 'id'>) => api<Rule>('/rules', { method: 'POST', body: JSON.stringify(body) }),
  updateRule: (id: string, body: Partial<Rule>) => api<Rule>(`/rules/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteRule: (id: string) => api<void>(`/rules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  patchCategory: (id: string, category_id: string, create_exact_rule: boolean) => api<Transaction>(`/transactions/${encodeURIComponent(id)}/category`, { method: 'PATCH', body: JSON.stringify({ category_id, create_exact_rule }) }),
  patchTransfer: (id: string, status: 'confirmed' | 'rejected') => api<Transaction>(`/transactions/${encodeURIComponent(id)}/transfer`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  patchClassification: (id: string, body: { classification: TransactionClassification; category_id?: string | null; create_exact_rule?: boolean }) => api<Transaction>(`/transactions/${encodeURIComponent(id)}/classification`, { method: 'PATCH', body: JSON.stringify(body) }),
  detectImport: (file: File) => { const form = new FormData(); form.append('file', file); return api<ImportDetection>('/imports/detect', { method: 'POST', body: form }) },
  previewImport: (file: File, account_id?: string) => { const form = new FormData(); form.append('file', file); if (account_id) form.append('account_id', account_id); return api<ImportResult>('/imports/preview', { method: 'POST', body: form }).then(normalizeImportResult) },
  importFile: (file: File, account_id?: string) => { const form = new FormData(); form.append('file', file); if (account_id) form.append('account_id', account_id); return api<ImportResult>('/imports', { method: 'POST', body: form }).then(normalizeImportResult) },
  exportWorkbook: () => `/api/export`
}

function normalizeImportResult(result: ImportResult): ImportResult {
  return { ...result, transfers: result.transfers ?? result.suspected_transfers ?? 0, review_required: result.review_required ?? 0, errors: (result.errors ?? []).map((item) => typeof item === 'string' ? { message: item } : item) }
}
