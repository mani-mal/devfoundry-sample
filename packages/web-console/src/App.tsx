import { lazy, Suspense, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import Navigation from './components/Navigation'
import ScrollToTop from './components/ScrollToTop'

const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const TasksPage = lazy(() => import('./pages/TasksPage'))
const TaskDetail = lazy(() => import('./pages/TaskDetail'))
const ProjectConfig = lazy(() => import('./pages/ProjectConfig'))
const ApplianceHealth = lazy(() => import('./pages/ApplianceHealth'))
const ModelGateway = lazy(() => import('./pages/ModelGateway'))
const Quality = lazy(() => import('./pages/Quality'))

function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="relative">
        <div className="h-16 w-16 border-4 border-primary-600/30 rounded-full animate-spin"></div>
        <div className="absolute top-0 left-0 h-16 w-16 border-4 border-primary-600 rounded-full border-t-transparent animate-spin"></div>
      </div>
    </div>
  )
}

function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const isAuthPage = location.pathname === '/login'

  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (!token && !isAuthPage) {
      window.location.href = '/login'
    }
    if (token && isAuthPage) {
      navigate('/dashboard', { replace: true })
    }
  }, [isAuthPage])

  if (isAuthPage) {
    return (
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <ScrollToTop />
      <Navigation />
      <main className="flex-1">
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
            <Route path="/project-config" element={<ProjectConfig />} />
            <Route path="/appliance-health" element={<ApplianceHealth />} />
            <Route path="/model-gateway" element={<ModelGateway />} />
            <Route path="/quality" element={<Quality />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}

export default App
