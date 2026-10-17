import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ThemeProvider } from '@/components/theme-provider'
import { AuthProvider } from '@/contexts/auth-provider'
import { WorkspaceProvider } from '@/contexts/workspace-provider'
import { CollectionFilterProvider } from '@/contexts/collection-filter-provider'
import { ProtectedRoute } from '@/components/protected-route'
import { AdminRoute } from '@/components/admin-route'
import { AgentsRoute } from '@/components/agents-route'
import { ModuleRoute } from '@/components/module-route'
import { AppLayout } from '@/components/app-layout'
import { HelpButton } from '@/components/help/help-button'

const SetupPage = lazy(() => import('@/pages/setup'))
const LoginPage = lazy(() => import('@/pages/login'))
const RegisterPage = lazy(() => import('@/pages/register'))
const ForgotPasswordPage = lazy(() => import('@/pages/forgot-password'))
const ResetPasswordPage = lazy(() => import('@/pages/reset-password'))
const HelpPage = lazy(() => import('@/pages/help'))
const DashboardPage = lazy(() => import('@/pages/dashboard'))
const TransactionsPage = lazy(() => import('@/pages/transactions'))
const AccountsPage = lazy(() => import('@/pages/accounts'))
const AccountDetailPage = lazy(() => import('@/pages/account-detail'))
const ImportPage = lazy(() => import('@/pages/import'))
const RulesPage = lazy(() => import('@/pages/rules'))
const CategoriesPage = lazy(() => import('@/pages/categories'))
const CollectionsPage = lazy(() => import('@/pages/collections'))
const BudgetsPage = lazy(() => import('@/pages/budgets'))
const RecurringPage = lazy(() => import('@/pages/recurring'))
const GoalsPage = lazy(() => import('@/pages/goals'))
const AssetsPage = lazy(() => import('@/pages/assets'))
const ReportsPage = lazy(() => import('@/pages/reports'))
const PayeesPage = lazy(() => import('@/pages/payees'))
const GroupsPage = lazy(() => import('@/pages/groups'))
const GroupDetailPage = lazy(() => import('@/pages/group-detail'))
const AdminSettingsPage = lazy(() => import('@/pages/admin/settings'))
const AgentsListPage = lazy(() => import('@/pages/agents-list'))
const AgentDetailPage = lazy(() => import('@/pages/agent-detail'))
const AgentConnectionsPage = lazy(() => import('@/pages/agent-connections'))
const InvoicesPage = lazy(() => import('@/pages/invoices'))
const InvoiceDetailPage = lazy(() => import('@/pages/invoice-detail'))
const ArApPage = lazy(() => import('@/pages/ar-ap'))
const DrePage = lazy(() => import('@/pages/dre'))
const SharedInvoicePage = lazy(() => import('@/pages/shared-invoice'))
const WorkspaceSettingsPage = lazy(() => import('@/pages/workspace-settings'))
const OnboardingEmpresaPage = lazy(() => import('@/pages/onboarding-empresa'))
const AuditPage = lazy(() => import('@/pages/audit'))
const PeriodsPage = lazy(() => import('@/pages/periods'))
const ApprovalsPage = lazy(() => import('@/pages/approvals'))
const PaymentsPage = lazy(() => import('@/pages/payments'))
const WebhooksPage = lazy(() => import('@/pages/webhooks'))
const ErpConnectionsPage = lazy(() => import('@/pages/erp-connections'))
const ConsolidatedPage = lazy(() => import('@/pages/consolidated'))
const CostCentersPage = lazy(() => import('@/pages/cost-centers'))
const AccrualsPage = lazy(() => import('@/pages/accruals'))
const AccessLogPage = lazy(() => import('@/pages/admin/access-log'))
const DataRequestsPage = lazy(() => import('@/pages/admin/data-requests'))
const OAuthCallbackPage = lazy(() => import('@/pages/oauth-callback'))
const OIDCCallbackPage = lazy(() => import('@/pages/oidc-callback'))
const SAMLCallbackPage = lazy(() => import('@/pages/saml-callback'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
    },
  },
})

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  )
}

function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
        <BrowserRouter>
          <AuthProvider>
            <WorkspaceProvider>
            <Suspense fallback={<LoadingFallback />}>
              <Routes>
                <Route path="/setup" element={<SetupPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/auth/oidc/callback" element={<OIDCCallbackPage />} />
                <Route path="/auth/saml/callback" element={<SAMLCallbackPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                <Route path="/reset-password" element={<ResetPasswordPage />} />
                {/* The manual is public: it is what you want open beside the login
                    screen before you have got in. */}
                <Route path="/help" element={<HelpPage />} />
                <Route path="/help/:topic" element={<HelpPage />} />
                {/* A client opening a link the sender shared. Deliberately
                    outside ProtectedRoute and outside AppLayout: the
                    recipient has no account, and the token is the whole
                    credential. */}
                <Route path="/i/:token" element={<SharedInvoicePage />} />
                <Route
                  element={
                    <ProtectedRoute>
                      <CollectionFilterProvider>
                        <AppLayout />
                      </CollectionFilterProvider>
                    </ProtectedRoute>
                  }
                >
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/transactions" element={<ModuleRoute module="transactions"><TransactionsPage /></ModuleRoute>} />
                  <Route path="/accounts" element={<ModuleRoute module="accounts"><AccountsPage /></ModuleRoute>} />
                  <Route path="/accounts/:id" element={<ModuleRoute module="accounts"><AccountDetailPage /></ModuleRoute>} />
                  <Route path="/oauth/callback" element={<OAuthCallbackPage />} />
                  <Route path="/enable-banking" element={<OAuthCallbackPage />} />
                  <Route path="/import" element={<ModuleRoute module="import"><ImportPage /></ModuleRoute>} />
                  <Route path="/rules" element={<ModuleRoute module="rules"><RulesPage /></ModuleRoute>} />
                  <Route path="/categories" element={<ModuleRoute module="categories"><CategoriesPage /></ModuleRoute>} />
                  <Route path="/collections" element={<CollectionsPage />} />
                  <Route path="/budgets" element={<ModuleRoute module="budgets"><BudgetsPage /></ModuleRoute>} />
                  <Route path="/goals" element={<ModuleRoute module="goals"><GoalsPage /></ModuleRoute>} />
                  <Route path="/recurring" element={<ModuleRoute module="recurring"><RecurringPage /></ModuleRoute>} />
                  <Route path="/assets" element={<ModuleRoute module="assets"><AssetsPage /></ModuleRoute>} />
                  {/* Kept so links minted before the importers were merged keep working. */}
                  <Route path="/assets/import" element={<Navigate to="/import?tab=investments" replace />} />
                  <Route path="/reports" element={<ModuleRoute module="reports"><ReportsPage /></ModuleRoute>} />
                  <Route path="/payees" element={<ModuleRoute module="payees"><PayeesPage /></ModuleRoute>} />
                  <Route path="/groups" element={<ModuleRoute module="split_groups"><GroupsPage /></ModuleRoute>} />
                  <Route path="/groups/:id" element={<ModuleRoute module="split_groups"><GroupDetailPage /></ModuleRoute>} />
                  <Route path="/invoices" element={<ModuleRoute module="invoices"><InvoicesPage /></ModuleRoute>} />
                  <Route path="/invoices/:id" element={<ModuleRoute module="invoices"><InvoiceDetailPage /></ModuleRoute>} />
                  <Route path="/cost-centers" element={<CostCentersPage />} />
                  <Route path="/accruals" element={<AccrualsPage />} />
                  <Route path="/ar-ap" element={<ModuleRoute module="ar_ap"><ArApPage /></ModuleRoute>} />
                  <Route path="/payments" element={<ModuleRoute module="ar_ap"><PaymentsPage /></ModuleRoute>} />
                  <Route path="/dre" element={<ModuleRoute module="reports"><DrePage /></ModuleRoute>} />
                  <Route path="/workspace/settings" element={<WorkspaceSettingsPage />} />
                  <Route path="/workspace/onboarding" element={<OnboardingEmpresaPage />} />
                  <Route path="/workspace/audit" element={<AuditPage />} />
                  <Route path="/workspace/periods" element={<PeriodsPage />} />
                  <Route path="/workspace/approvals" element={<ApprovalsPage />} />
                  <Route path="/workspace/webhooks" element={<WebhooksPage />} />
                  <Route path="/workspace/erp" element={<ErpConnectionsPage />} />
                  <Route path="/consolidated" element={<ConsolidatedPage />} />
                  <Route path="/admin" element={<AdminRoute><AdminSettingsPage /></AdminRoute>} />
                  <Route path="/admin/access-log" element={<AdminRoute><AccessLogPage /></AdminRoute>} />
                  <Route path="/admin/data-requests" element={<AdminRoute><DataRequestsPage /></AdminRoute>} />
                  <Route path="/agents" element={<AgentsRoute><AgentsListPage /></AgentsRoute>} />
                  <Route path="/agents/connections" element={<AgentsRoute><AgentConnectionsPage /></AgentsRoute>} />
                  <Route path="/agents/:id" element={<AgentsRoute><AgentDetailPage /></AgentsRoute>} />
                </Route>
              </Routes>
            </Suspense>
            <Toaster />
            {/* One help button for every screen, mounted here so none can forget it. */}
            <HelpButton />
            </WorkspaceProvider>
          </AuthProvider>
        </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export default App
