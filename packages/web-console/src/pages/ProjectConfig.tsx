import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardActions } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Select } from '../components/ui/Select';
import { apiClient } from '../lib/api';
import { 
  Database, 
  Wrench, 
  Code, 
  Plus,
  Edit,
  Trash2,
  Settings,
  CheckCircle,
  AlertCircle,
  Lock,
  Globe,
  HardDrive
} from 'lucide-react';

interface Repository {
  id: string;
  name: string;
  url: string;
  branch: string;
  enabled: boolean;
}

interface Tool {
  id: string;
  name: string;
  kind: string;
  description?: string;
  scopes: string[];
  enabled: boolean;
}

interface Skill {
  id: string;
  name: string;
  version: string;
  digest: string;
  description?: string;
  status: string;
}

interface ContextStats {
  nodes: number;
  edges: number;
  chunks: number;
}

export default function ProjectConfig() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [contextStats, setContextStats] = useState<ContextStats | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'repositories' | 'tools' | 'skills'>('repositories');

  useEffect(() => {
    const load = async () => {
      try {
        const [toolsRes, skillsRes, statsRes] = await Promise.all([
          apiClient.getTools(),
          apiClient.getSkills(),
          apiClient.getContextStats().catch(() => null),
        ]);
        setTools(toolsRes.tools.map((t) => ({ id: t.id, name: t.name, kind: t.kind, description: t.description, scopes: t.scopes, enabled: t.enabled })));
        setSkills(skillsRes.skills.map((s) => ({ id: s.id, name: s.name, version: s.version, digest: s.digest, description: s.description, status: s.approvalStatus })));
        if (statsRes) setContextStats(statsRes);
        setLoadError(null);
      } catch (err) {
        setLoadError((err as Error).message);
      }
    };
    void load();
  }, []);

  const handleToggleTool = async (id: string) => {
    const tool = tools.find((t) => t.id === id);
    if (!tool) return;
    const next = !tool.enabled;
    try {
      await apiClient.setToolEnabled(id, next);
      setTools((prev) => prev.map((t) => (t.id === id ? { ...t, enabled: next } : t)));
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handlePromoteSkill = async (id: string) => {
    try {
      await apiClient.setSkillStatus(id, 'approved');
      setSkills((prev) => prev.map((s) => (s.id === id ? { ...s, status: 'approved' } : s)));
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'published':
        return 'success';
      case 'approved':
        return 'info';
      case 'draft':
        return 'default';
      case 'deprecated':
        return 'danger';
      default:
        return 'default';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'published':
        return <CheckCircle className="h-3 w-3" />;
      case 'approved':
        return <CheckCircle className="h-3 w-3" />;
      case 'linted':
      case 'sandbox-tested':
      case 'evaluated':
        return <Settings className="h-3 w-3" />;
      case 'draft':
        return <Settings className="h-3 w-3" />;
      case 'deprecated':
        return <AlertCircle className="h-3 w-3" />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-dashboard-bg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 animate-fade-in-up">
          <div>
            <h1 className="text-3xl font-bold text-dashboard-text mb-2">Project Configuration</h1>
            <p className="text-dashboard-muted">Manage repositories, tools, and skills for this project</p>
          </div>
        </div>

        {/* Context Status */}
        {loadError && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
            Failed to load configuration: {loadError}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card variant="elevated">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-dashboard-muted mb-1">Context Graph</p>
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-5 w-5 text-emerald-400" />
                    <span className="text-2xl font-bold text-dashboard-text">
                      {contextStats ? `${contextStats.nodes} nodes` : '—'}
                    </span>
                  </div>
                </div>
                <div className="h-12 w-12 bg-emerald-500/20 rounded-xl flex items-center justify-center">
                  <CheckCircle className="h-6 w-6 text-emerald-400" />
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-dashboard-border/50">
                <p className="text-xs text-dashboard-muted">
                  {contextStats ? `${contextStats.edges} edges · ${contextStats.chunks} chunks` : 'Context service unavailable'}
                </p>
              </div>
            </CardContent>
          </Card>
          <Card variant="elevated">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-dashboard-muted mb-1">Approved Tools</p>
                  <div className="flex items-center gap-2">
                    <Database className="h-5 w-5 text-primary-400" />
                    <span className="text-2xl font-bold text-dashboard-text">{tools.filter((t) => t.enabled).length}/{tools.length}</span>
                  </div>
                </div>
                <div className="h-12 w-12 bg-primary-500/20 rounded-xl flex items-center justify-center">
                  <Database className="h-6 w-6 text-primary-400" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card variant="elevated">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-dashboard-muted mb-1">Installed Skills</p>
                  <div className="flex items-center gap-2">
                    <HardDrive className="h-5 w-5 text-purple-400" />
                    <span className="text-2xl font-bold text-dashboard-text">
                      {skills.filter((s) => s.status === 'approved' || s.status === 'published').length}/{skills.length}
                    </span>
                  </div>
                </div>
                <div className="h-12 w-12 bg-purple-500/20 rounded-xl flex items-center justify-center">
                  <HardDrive className="h-6 w-6 text-purple-400" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <Card variant="elevated">
          <div className="flex border-b border-dashboard-border">
            <button
              className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'repositories' 
                  ? 'border-primary-500 text-primary-400 bg-primary-500/5' 
                  : 'border-transparent text-dashboard-text-secondary hover:text-dashboard-text hover:bg-dashboard-card/30'
              }`}
              onClick={() => setActiveTab('repositories')}
            >
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4" />
                Repositories
              </div>
            </button>
            <button
              className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'tools' 
                  ? 'border-primary-500 text-primary-400 bg-primary-500/5' 
                  : 'border-transparent text-dashboard-text-secondary hover:text-dashboard-text hover:bg-dashboard-card/30'
              }`}
              onClick={() => setActiveTab('tools')}
            >
              <div className="flex items-center gap-2">
                <Wrench className="h-4 w-4" />
                Tools
              </div>
            </button>
            <button
              className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'skills' 
                  ? 'border-primary-500 text-primary-400 bg-primary-500/5' 
                  : 'border-transparent text-dashboard-text-secondary hover:text-dashboard-text hover:bg-dashboard-card/30'
              }`}
              onClick={() => setActiveTab('skills')}
            >
              <div className="flex items-center gap-2">
                <Code className="h-4 w-4" />
                Skills
              </div>
            </button>
          </div>

          <CardContent className="p-6">
            {activeTab === 'repositories' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-dashboard-text">Repository List</h3>
                  <Button variant="primary" size="sm" leftIcon={<Plus className="h-4 w-4" />}>
                    Add Repository
                  </Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                      <tr>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Name</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">URL</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Branch</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dashboard-border">
                      {repositories.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-8 text-center text-sm text-dashboard-muted">
                            No repositories registered yet. Use the CLI: <code className="text-primary-400">devfoundry project create</code>
                          </td>
                        </tr>
                      )}
                      {repositories.map(repo => (
                        <tr key={repo.id} className="hover:bg-dashboard-card/30 transition-colors">
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              {repo.enabled ? (
                                <CheckCircle className="h-4 w-4 text-emerald-400" />
                              ) : (
                                <div className="h-4 w-4 rounded-full border-2 border-dashboard-border" />
                              )}
                              <span className="text-sm font-medium text-dashboard-text">{repo.name}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-sm text-dashboard-text-secondary truncate max-w-[200px]" title={repo.url}>
                              {repo.url}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-sm text-dashboard-text-secondary">{repo.branch}</span>
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant={repo.enabled ? 'success' : 'default'}>
                              {repo.enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <Button variant="ghost" size="sm" title="Edit">
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button variant="ghost" size="sm" title="Remove" className="text-red-400 hover:text-red-300 hover:bg-red-500/10">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'tools' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-dashboard-text">Approved Tools</h3>
                  <Button variant="primary" size="sm" leftIcon={<Plus className="h-4 w-4" />}>
                    Add Tool
                  </Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                      <tr>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Tool</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Kind</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Scopes</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dashboard-border">
                      {tools.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-8 text-center text-sm text-dashboard-muted">
                            No tools registered. Register via <code className="text-primary-400">POST /api/tools</code>
                          </td>
                        </tr>
                      )}
                      {tools.map(tool => (
                        <tr key={tool.id} className="hover:bg-dashboard-card/30 transition-colors">
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <Wrench className="h-4 w-4 text-dashboard-muted" />
                              <span className="text-sm font-medium text-dashboard-text">{tool.name}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-sm text-dashboard-text-secondary">{tool.kind}</span>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex flex-wrap gap-1">
                              {tool.scopes.map(scope => (
                                <span key={scope} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-dashboard-muted/20 text-dashboard-muted">
                                  {scope}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant={tool.enabled ? 'success' : 'default'}>
                              {tool.enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <Button 
                              variant={tool.enabled ? 'secondary' : 'primary'} 
                              size="sm" 
                              onClick={() => handleToggleTool(tool.id)}
                            >
                              {tool.enabled ? 'Disable' : 'Enable'}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'skills' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-dashboard-text">Project Skills</h3>
                  <Button variant="primary" size="sm" leftIcon={<Plus className="h-4 w-4" />}>
                    Install Skill
                  </Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                      <tr>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Skill</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Version</th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dashboard-border">
                      {skills.length === 0 && (
                        <tr>
                          <td colSpan={4} className="py-8 text-center text-sm text-dashboard-muted">
                            No skills installed. Install via <code className="text-primary-400">devfoundry skill install</code>
                          </td>
                        </tr>
                      )}
                      {skills.map(skill => (
                        <tr key={skill.id} className="hover:bg-dashboard-card/30 transition-colors">
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <Code className="h-4 w-4 text-primary-400" />
                              <span className="text-sm font-medium text-dashboard-text">{skill.name}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-sm text-dashboard-text-secondary">{skill.version}</span>
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant={getStatusColor(skill.status)} className="flex items-center gap-1">
                              {getStatusIcon(skill.status)}
                              {skill.status}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {skill.status !== 'approved' && skill.status !== 'published' && (
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => handlePromoteSkill(skill.id)}
                                >
                                  Approve
                                </Button>
                              )}
                              <Button variant="ghost" size="sm" title="Configure">
                                <Settings className="h-4 w-4" />
                              </Button>
                              <Button variant="ghost" size="sm" title="Uninstall" className="text-red-400 hover:text-red-300 hover:bg-red-500/10">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
