import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { apiClient } from '../lib/api';
import { 
  Lock, 
  Mail,
  ChevronRight
} from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await apiClient.login(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError('Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-dashboard-bg via-primary-950/30 to-dashboard-bg px-4">
      <div className="w-full max-w-md">
        {/* Logo Section */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-20 w-20 bg-gradient-to-br from-primary-600 to-primary-700 rounded-2xl shadow-2xl shadow-primary-500/30 mb-6">
            <span className="text-4xl font-bold text-white">D</span>
          </div>
          <h1 className="text-4xl font-bold text-dashboard-text mb-2 tracking-tight">DevFoundry</h1>
          <p className="text-dashboard-muted">Admin Console</p>
        </div>

        {/* Login Form */}
        <Card className="backdrop-blur-sm">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
              <Input
                label="Email Address"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@devfoundry.local"
                leftIcon={<Mail className="h-4 w-4" />}
                required
              />

              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                leftIcon={<Lock className="h-4 w-4" />}
                required
              />
            </div>

            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-3">
                <div className="h-5 w-5 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0">
                  <svg className="h-3 w-3 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            <Button 
              type="submit" 
              className="w-full group" 
              disabled={loading}
              size="lg"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="h-4 w-4 border-2 border-white/30 rounded-full animate-spin" />
                  <span>Signing in...</span>
                </div>
              ) : (
                <span className="flex items-center gap-2">
                  Sign In <ChevronRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                </span>
              )}
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-dashboard-border">
            <div className="bg-dashboard-card/50 rounded-lg p-4">
              <p className="text-xs font-medium text-dashboard-muted mb-3">Default credentials:</p>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="p-3 bg-dashboard-card rounded-lg border border-dashboard-border">
                  <p className="text-dashboard-muted mb-1">Email</p>
                  <p className="font-medium text-dashboard-text">admin@devfoundry.local</p>
                </div>
                <div className="p-3 bg-dashboard-card rounded-lg border border-dashboard-border">
                  <p className="text-dashboard-muted mb-1">Password</p>
                  <p className="font-medium text-dashboard-text">devfoundry</p>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Footer */}
        <div className="text-center mt-8">
          <p className="text-sm text-dashboard-muted">
            &copy; {new Date().getFullYear()} DevFoundry. All rights reserved.
          </p>
        </div>
      </div>
    </div>
  );
}
