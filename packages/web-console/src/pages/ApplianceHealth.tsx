import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { apiClient } from '../lib/api';
import { 
  Cpu, 
  MemoryStick, 
  HardDrive, 
  Activity, 
  Server,
  Thermometer,
  Zap,
  CheckCircle,
  AlertCircle,
  Clock
} from 'lucide-react';

interface ServiceStatus {
  name: string;
  status: 'healthy' | 'unhealthy' | 'degraded';
  uptime: number;
  lastCheck: string;
}

interface ResourceUsage {
  cpu: number;
  memory: number;
  disk: number;
  gpu?: {
    usage: number;
    memoryUsage: number;
    temperature: number;
  };
}

const ProgressBar = ({ 
  value, 
  color, 
  label 
}: { 
  value: number; 
  color: string; 
  label?: string;
}) => {
  return (
    <div className="space-y-2">
      {label && (
        <div className="flex justify-between text-sm">
          <span className="text-dashboard-text-secondary">{label}</span>
          <span className="text-dashboard-text font-medium">{value.toFixed(1)}%</span>
        </div>
      )}
      <div className="h-3 bg-dashboard-muted/30 rounded-full overflow-hidden">
        <div 
          className={`h-full ${color} transition-all duration-500 ease-out rounded-full`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
};

export default function ApplianceHealth() {
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [resources, setResources] = useState<ResourceUsage>({
    cpu: 0,
    memory: 0,
    disk: 0,
    gpu: undefined,
  });
  const [hardwareProfile, setHardwareProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchHealthData();
    const interval = setInterval(fetchHealthData, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchHealthData = async () => {
    try {
      const health = await apiClient.getApplianceHealth();
      
       setServices([
         { 
           name: 'API Service', 
           status: health.services?.api?.status || 'ok', 
           uptime: health.services?.api?.uptime || 0,
           lastCheck: new Date().toISOString() 
         },
         { 
           name: 'Worker Service', 
           status: health.services?.worker?.status || 'ok', 
           uptime: health.services?.worker?.uptime || 0,
           lastCheck: new Date().toISOString() 
         },
         { 
           name: 'PostgreSQL', 
           status: health.services?.database?.status || 'connected', 
           uptime: health.services?.database?.uptime || 0,
           lastCheck: new Date().toISOString() 
         },
         { 
           name: 'RouteForge', 
           status: health.services?.routeforge?.status || 'ok', 
           uptime: health.services?.routeforge?.uptime || 0,
           lastCheck: new Date().toISOString() 
         },
         { 
           name: 'ContextForge', 
           status: health.services?.contextForge?.status || 'ok', 
           uptime: health.services?.contextForge?.uptime || 0,
           lastCheck: new Date().toISOString() 
         },
         { 
           name: 'Langfuse', 
           status: health.services?.langfuse?.status || 'ok', 
           uptime: health.services?.langfuse?.uptime || 0,
           lastCheck: new Date().toISOString() 
         },
       ]);

      setResources({
        cpu: health.resources?.cpu?.usage || 0,
        memory: health.resources?.memory?.usage || 0,
        disk: health.resources?.disk?.usage || 0,
        gpu: health.resources?.gpu,
      });

      setHardwareProfile({
        name: 'DGX Spark Compact',
        cpu: { cores: 20, ram: 128 },
        gpu: { type: 'H200', count: 8, vram: 141 },
      });

      setLoading(false);
    } catch (error) {
      setLoading(false);
    }
  };

  const normalizeStatus = (status: string): 'healthy' | 'unhealthy' | 'degraded' => {
    switch (status) {
      case 'ok':
      case 'connected':
      case 'healthy':
        return 'healthy';
      case 'unavailable':
      case 'unhealthy':
      case 'error':
        return 'unhealthy';
      case 'degraded':
        return 'degraded';
      default:
        return 'healthy';
    }
  };

  const getStatusColor = (status: string) => {
    switch (normalizeStatus(status)) {
      case 'healthy':
        return 'bg-emerald-500';
      case 'unhealthy':
        return 'bg-red-500';
      case 'degraded':
        return 'bg-amber-500';
      default:
        return 'bg-dashboard-muted';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (normalizeStatus(status)) {
      case 'healthy':
        return <CheckCircle className="h-5 w-5 text-emerald-400" />;
      case 'unhealthy':
        return <AlertCircle className="h-5 w-5 text-red-400" />;
      case 'degraded':
        return <AlertCircle className="h-5 w-5 text-amber-400" />;
      default:
        return <CheckCircle className="h-5 w-5 text-dashboard-muted" />;
    }
  };

  const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="relative">
          <div className="h-16 w-16 border-4 border-primary-600/30 rounded-full animate-spin"></div>
          <div className="absolute top-0 left-0 h-16 w-16 border-4 border-primary-600 rounded-full border-t-transparent animate-spin"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dashboard-bg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 animate-fade-in-up">
          <div>
            <h1 className="text-3xl font-bold text-dashboard-text mb-2">Appliance Health</h1>
            <p className="text-dashboard-muted">System resources, services, and hardware status</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 bg-dashboard-card px-4 py-2 rounded-lg border border-dashboard-border">
              <div className="h-3 w-3 rounded-full bg-emerald-500 animate-pulse"></div>
              <span className="text-sm font-medium text-dashboard-text">Online</span>
            </div>
          </div>
        </div>

        <Card variant="elevated" className="mb-6">
          <CardHeader>
            <CardTitle>
              <Server className="h-5 w-5 text-primary-400" />
              Hardware Profile
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-6 bg-dashboard-card/50 rounded-xl border border-dashboard-border/50">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-3 bg-primary-500/20 rounded-lg">
                    <Server className="h-6 w-6 text-primary-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-dashboard-muted">Profile</p>
                    <p className="text-lg font-semibold text-dashboard-text">{hardwareProfile?.name}</p>
                  </div>
                </div>
              </div>
              <div className="p-6 bg-dashboard-card/50 rounded-xl border border-dashboard-border/50">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-3 bg-blue-500/20 rounded-lg">
                    <Cpu className="h-6 w-6 text-blue-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-dashboard-muted">CPU</p>
                    <div className="space-y-1 mt-2">
                      <p className="text-lg font-semibold text-dashboard-text">{hardwareProfile?.cpu?.cores} cores</p>
                      <p className="text-sm text-dashboard-muted">{hardwareProfile?.cpu?.ram} GB RAM</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="p-6 bg-dashboard-card/50 rounded-xl border border-dashboard-border/50">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-3 bg-red-500/20 rounded-lg">
                    <Activity className="h-6 w-6 text-red-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-dashboard-muted">GPU</p>
                    <div className="space-y-1 mt-2">
                      <p className="text-lg font-semibold text-dashboard-text">{hardwareProfile?.gpu?.count} × {hardwareProfile?.gpu?.type}</p>
                      <p className="text-sm text-dashboard-muted">{hardwareProfile?.gpu?.vram} GB VRAM</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <Card variant="elevated">
            <CardHeader>
              <CardTitle>
                <Cpu className="h-5 w-5 text-blue-400" />
                CPU Usage
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <ProgressBar 
                value={resources.cpu} 
                color="bg-blue-500" 
                label="CPU Usage"
              />
              <div className="mt-6 grid grid-cols-2 gap-4">
                <div className="p-4 bg-dashboard-card/50 rounded-lg">
                  <p className="text-sm text-dashboard-muted mb-1">Load Average</p>
                  <p className="text-lg font-semibold text-dashboard-text">2.4, 1.8, 1.2</p>
                </div>
                <div className="p-4 bg-dashboard-card/50 rounded-lg">
                  <p className="text-sm text-dashboard-muted mb-1">Processes</p>
                  <p className="text-lg font-semibold text-dashboard-text">248</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card variant="elevated">
            <CardHeader>
              <CardTitle>
                <MemoryStick className="h-5 w-5 text-purple-400" />
                Memory Usage
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <ProgressBar 
                value={resources.memory} 
                color="bg-purple-500" 
                label="Memory Usage"
              />
              <div className="mt-6 grid grid-cols-2 gap-4">
                <div className="p-4 bg-dashboard-card/50 rounded-lg">
                  <p className="text-sm text-dashboard-muted mb-1">Total</p>
                  <p className="text-lg font-semibold text-dashboard-text">128 GB</p>
                </div>
                <div className="p-4 bg-dashboard-card/50 rounded-lg">
                  <p className="text-sm text-dashboard-muted mb-1">Used</p>
                  <p className="text-lg font-semibold text-dashboard-text">{(128 * resources.memory / 100).toFixed(1)} GB</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card variant="elevated">
            <CardHeader>
              <CardTitle>
                <HardDrive className="h-5 w-5 text-emerald-400" />
                Disk Usage
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <ProgressBar 
                value={resources.disk} 
                color="bg-emerald-500" 
                label="Disk Usage"
              />
              <div className="mt-6 grid grid-cols-2 gap-4">
                <div className="p-4 bg-dashboard-card/50 rounded-lg">
                  <p className="text-sm text-dashboard-muted mb-1">Total</p>
                  <p className="text-lg font-semibold text-dashboard-text">100 GB</p>
                </div>
                <div className="p-4 bg-dashboard-card/50 rounded-lg">
                  <p className="text-sm text-dashboard-muted mb-1">Used</p>
                  <p className="text-lg font-semibold text-dashboard-text">{(100 * resources.disk / 100).toFixed(1)} GB</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {resources.gpu && (
          <Card variant="elevated" className="mb-6">
            <CardHeader>
              <CardTitle>
                <Activity className="h-5 w-5 text-red-400" />
                GPU Usage
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="space-y-4">
                  <ProgressBar 
                    value={resources.gpu.usage} 
                    color="bg-red-500" 
                    label="GPU Utilization"
                  />
                  <ProgressBar 
                    value={resources.gpu.memoryUsage} 
                    color="bg-orange-500" 
                    label="Memory Usage"
                  />
                </div>
                <div className="p-4 bg-dashboard-card/50 rounded-xl border border-dashboard-border/50">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-3 bg-amber-500/20 rounded-lg">
                      <Thermometer className="h-6 w-6 text-amber-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-dashboard-muted">Temperature</p>
                      <p className="text-2xl font-semibold text-dashboard-text">{resources.gpu.temperature}°C</p>
                    </div>
                  </div>
                </div>
                <div className="p-4 bg-dashboard-card/50 rounded-xl border border-dashboard-border/50">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-3 bg-yellow-500/20 rounded-lg">
                      <Zap className="h-6 w-6 text-yellow-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-dashboard-muted">Power</p>
                      <p className="text-2xl font-semibold text-dashboard-text">250 W</p>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card variant="elevated">
          <CardHeader>
            <CardTitle>
              <Activity className="h-5 w-5 text-primary-400" />
              Service Health
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                  <tr>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Service</th>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Uptime</th>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Last Check</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dashboard-border">
                  {services.map((service, idx) => (
                    <tr key={idx} className="hover:bg-dashboard-card/30 transition-colors">
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <div className={`h-3 w-3 rounded-full ${getStatusColor(service.status)} animate-pulse`} />
                          <span className="text-sm font-medium text-dashboard-text">{service.name}</span>
                        </div>
                      </td>
                       <td className="py-4 px-6">
                         <Badge 
                           variant={
                             normalizeStatus(service.status) === 'healthy' ? 'success' : 
                             normalizeStatus(service.status) === 'degraded' ? 'warning' : 'danger'
                           }
                         >
                           {normalizeStatus(service.status).charAt(0).toUpperCase() + normalizeStatus(service.status).slice(1)}
                         </Badge>
                       </td>
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2 text-sm text-dashboard-text-secondary">
                          <Clock className="h-4 w-4" />
                          {formatUptime(service.uptime)}
                        </div>
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm text-dashboard-muted">
                          {new Date(service.lastCheck).toLocaleTimeString()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
