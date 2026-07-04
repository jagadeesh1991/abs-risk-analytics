import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Comparison from './pages/Comparison'
import Distributions from './pages/Distributions'
import Geography from './pages/Geography'
import Overview from './pages/Overview'
import Performance from './pages/Performance'
import Prepayment from './pages/Prepayment'
import Stratification from './pages/Stratification'
import Structuring from './pages/Structuring'
import Surveillance from './pages/Surveillance'
import Transitions from './pages/Transitions'
import Upload from './pages/Upload'
import Vintage from './pages/Vintage'
import { AppProvider } from './state/AppContext'

export default function App() {
  return (
    <AppProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/surveillance" element={<Surveillance />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/vintage" element={<Vintage />} />
          <Route path="/stratification" element={<Stratification />} />
          <Route path="/distributions" element={<Distributions />} />
          <Route path="/geography" element={<Geography />} />
          <Route path="/transitions" element={<Transitions />} />
          <Route path="/prepayment" element={<Prepayment />} />
          <Route path="/comparison" element={<Comparison />} />
          <Route path="/structuring" element={<Navigate to="/structuring/abs" replace />} />
          <Route path="/structuring/abs" element={<Structuring dealType="abs" />} />
          <Route path="/structuring/clo" element={<Structuring dealType="clo" />} />
          <Route path="/structuring/rmbs" element={<Structuring dealType="rmbs" />} />
          <Route path="/upload" element={<Upload />} />
        </Route>
      </Routes>
    </AppProvider>
  )
}
