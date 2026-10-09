import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Button } from '../components/ui/Button';

export default function Navigation() {
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const navItems = [
    { name: 'Dashboard', path: '/dashboard' },
    { name: 'Tasks', path: '/tasks' },
    { name: 'Project Config', path: '/project-config' },
    { name: 'Appliance Health', path: '/appliance-health' },
  ];

  const isActive = (path: string) => location.pathname === path;

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-dashboard-border bg-dashboard-bg/95 backdrop-blur supports-[backdrop-filter]:bg-dashboard-bg/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="flex items-center gap-2">
              <div className="h-10 w-10 bg-gradient-to-br from-primary-600 to-primary-700 rounded-xl flex items-center justify-center shadow-lg shadow-primary-500/20">
                <span className="text-white font-bold text-xl">D</span>
              </div>
              <span className="text-xl font-bold bg-gradient-to-r from-dashboard-text to-dashboard-muted bg-clip-text text-transparent hidden sm:block">
                DevFoundry
              </span>
            </Link>
          </div>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive(item.path)
                    ? 'bg-primary-600 text-white shadow-lg shadow-primary-500/20'
                    : 'text-dashboard-text-secondary hover:bg-dashboard-muted hover:text-dashboard-text'
                }`}
              >
                {item.name}
              </Link>
            ))}
            <div className="ml-4 pl-4 border-l border-dashboard-border">
              <Button 
                variant="secondary" 
                size="sm" 
                onClick={() => {
                  localStorage.removeItem('authToken');
                  window.location.href = '/login';
                }}
              >
                Logout
              </Button>
            </div>
          </div>

          {/* Mobile menu button */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="text-dashboard-text-secondary hover:text-dashboard-text p-2 rounded-lg hover:bg-dashboard-muted transition-colors"
            >
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation */}
      {isMenuOpen && (
        <div className="md:hidden border-b border-dashboard-border bg-dashboard-card">
          <div className="px-2 pt-2 pb-4 space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`block px-4 py-3 rounded-lg text-base font-medium ${
                  isActive(item.path)
                    ? 'bg-primary-600/10 text-primary-400'
                    : 'text-dashboard-text-secondary hover:bg-dashboard-muted hover:text-dashboard-text'
                }`}
                onClick={() => setIsMenuOpen(false)}
              >
                {item.name}
              </Link>
            ))}
            <button
              onClick={() => {
                localStorage.removeItem('authToken');
                window.location.href = '/login';
              }}
              className="block w-full text-left px-4 py-3 rounded-lg text-base font-medium text-red-400 hover:bg-red-500/10"
            >
              Logout
            </button>
          </div>
        </div>
      )}
    </nav>
  );
}
