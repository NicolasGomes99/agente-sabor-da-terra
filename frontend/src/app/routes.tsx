import { Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom'

import { LoginPage } from '../features/auth/pages/LoginPage'
import { useAuth } from '../features/auth/useAuth'
import { ChatPage } from '../features/chat/pages/ChatPage'
import { DocumentsPage } from '../features/documents/pages/DocumentsPage'
import { OrderDetailPage } from '../features/orders/pages/OrderDetailPage'
import { OrderFormPage } from '../features/orders/pages/OrderFormPage'
import { OrdersPage } from '../features/orders/pages/OrdersPage'
import { ProducerDetailPage } from '../features/registry/pages/ProducerDetailPage'
import { ProducersPage } from '../features/registry/pages/ProducersPage'
import { ProductsPage } from '../features/registry/pages/ProductsPage'

function PublicRoute() {
  const { isAuthenticated } = useAuth()

  return isAuthenticated ? <Navigate to="/chat" replace /> : <Outlet />
}

function ProtectedRoute() {
  const { isAuthenticated } = useAuth()

  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
}

function LoginRoute() {
  const navigate = useNavigate()

  return <LoginPage onAuthenticated={() => navigate('/chat', { replace: true })} />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicRoute />}>
        <Route path="/login" element={<LoginRoute />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/new" element={<OrderFormPage />} />
        <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        <Route path="/orders/:orderId/edit" element={<OrderFormPage />} />
        <Route path="/registry" element={<Navigate to="/registry/products" replace />} />
        <Route path="/registry/products" element={<ProductsPage />} />
        <Route path="/registry/producers" element={<ProducersPage />} />
        <Route path="/registry/producers/:producerId" element={<ProducerDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
