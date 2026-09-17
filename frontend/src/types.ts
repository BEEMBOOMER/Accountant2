export type Page = 'dashboard' | 'import' | 'transactions' | 'settings'

export type Account = { id: string; bank: string; name: string; identifier: string; is_savings: boolean }
export type Category = { id: string; name: string; transaction_count?: number; color?: string }
export type Rule = { id: string; kind: 'merchant' | 'keyword'; pattern: string; category_id: string; enabled: boolean }
export type Transaction = {
  id: string; date: string; bank: string; account: string; original_description: string
  normalized_description?: string; amount: number; type: string; category_id?: string | null
  classification?: TransactionClassification
  category?: string | null; transfer_status?: 'none' | 'suspected' | 'confirmed' | 'rejected'
  internal_transfer?: boolean; savings_transfer?: boolean; expense_reimbursement?: boolean; review_required?: boolean; source_file?: string
}
export type TransactionClassification = 'expense' | 'income' | 'transfer' | 'savings' | 'investment' | 'reimbursement'
export type Analytics = {
  month?: string; income: number; expenditure: number; savings: number; investments?: number; net_cashflow: number
  spending_by_category?: Array<{ category: string; name?: string; amount: number; value?: number; color?: string }>
  top_categories?: Array<{ category: string; name?: string; amount: number; value?: number }>
  top_expenses?: Array<{ description: string; amount: number; date?: string; category?: string }>
}
export type AnalyticsMonths = { months: string[]; latest: string | null }
export type ImportDetection = { bank: 'CommBank' | 'Westpac'; account_required: boolean }
export type ImportResult = { bank?: 'CommBank' | 'Westpac'; processed: number; inserted: number; duplicates: number; transfers?: number; suspected_transfers?: number; review_required: number; rejected?: number; latest_month?: string | null; errors: Array<{ row?: number; message: string } | string> }
