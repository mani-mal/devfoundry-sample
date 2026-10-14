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
  HardDrive,
  X
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
  endpoint?: string;
  transport?: string;
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

interface ToolForm {
  name: string;
  kind: string;
  description: string;
  endpoint: string;
  transport: string;
  scopes: string;
}

const EMPTY_TOOL_FORM: ToolForm = {
  name: '',
  kind: 'http',
  description: '',
  endpoint: '',
  transport: 'http',
  scopes: '',
};

interface SkillForm {
  name: string;
  path: string;
  gitRepository: string;
  version: string;
  description: string;
}

const EMPTY_SKILL_FORM: SkillForm = {
  name: '',
  path: '',
  gitRepository: 'local://defaults',
  version: '1.0.0',
  description: '',
};

export default function ProjectConfig() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [contextStats, setContextStats] = useState<ContextStats | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'repositories' | 'tools' | 'skills'>('repositories');
  const [showAddTool, setShowAddTool] = useState(false);
  const [toolForm, setToolForm] = useState<ToolForm>(EMPTY_TOOL_FORM);
  const [savingTool, setSavingTool] = useState(false);
  const [showInstallSkill, setShowInstallSkill] = useState(false);
  const [skillForm, setSkillForm] = useState<SkillForm>(EMPTY_SKILL_FORM);
  const [savingSkill, setSavingSkill] = useState(false);
  const [showRepoInfo, setShowRepoInfo] = useState(false);
  const [openTool, setOpenTool] = useState<Tool | null>(null);
  const [toolDraft, setToolDraft] = useState<ToolForm>(EMPTY_TOOL_FORM);
  const [savingToolEdit, setSavingToolEdit] = useState(false);
  const [openSkill, setOpenSkill] = useState<Skill | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [toolsRes, skillsRes, statsRes] = await Promise.all([
        apiClient.getTools(),
        apiClient.getSkills(),
        apiClient.getContextStats().catch(() => null),
      ]);
      setTools(toolsRes.tools.map((t) => ({ id: t.id, name: t.name, kind: t.kind, description: t.description, endpoint: t.endpoint, transport: t.transport, scopes: t.scopes, enabled: t.enabled })));
      setSkills(skillsRes.skills.map((s) => ({ id: s.id, name: s.name, version: s.version, digest: s.digest, description: s.description, status: s.approvalStatus })));
      if (statsRes) setContextStats(statsRes);
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleAddTool = async () => {
    if (!toolForm.name.trim()) {
      setFormError('Tool name is required.');
      return;
    }
    setSavingTool(true);
    setFormError(null);
    try {
      await apiClient.createTool({
        name: toolForm.name.trim(),
        kind: toolForm.kind,
        description: toolForm.description.trim() || undefined,
        endpoint: toolForm.endpoint.trim() || undefined,
        transport: toolForm.transport,
        scopes: toolForm.scopes.split(',').map((s) => s.trim()).filter(Boolean),
        enabled: false,
      });
      setShowAddTool(false);
      setToolForm(EMPTY_TOOL_FORM);
      await load();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSavingTool(false);
    }
  };

  const handleInstallSkill = async () => {
    if (!skillForm.name.trim() || !skillForm.path.trim() || !skillForm.gitRepository.trim()) {
      setFormError('Name, path, and git repository are required.');
      return;
    }
    setSavingSkill(true);
    setFormError(null);
    try {
      await apiClient.installSkill({
        name: skillForm.name.trim(),
        path: skillForm.path.trim(),
        gitRepository: skillForm.gitRepository.trim(),
        version: skillForm.version.trim() || '1.0.0',
        description: skillForm.description.trim() || undefined,
      });
      setShowInstallSkill(false);
      setSkillForm(EMPTY_SKILL_FORM);
      await load();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSavingSkill(false);
    }
  };

  const handleOpenTool = (tool: Tool) => {
    setOpenTool(tool);
    setToolDraft({
      name: tool.name,
      kind: tool.kind,
      description: tool.description ?? '',
      endpoint: tool.endpoint ?? '',
      transport: tool.transport ?? 'http',
      scopes: tool.scopes.join(', '),
    });
    setFormError(null);
  };

  const handleSaveTool = async () => {
    if (!openTool) return;
    setSavingToolEdit(true);
    setFormError(null);
    try {
      await apiClient.updateTool(openTool.id, {
        name: toolDraft.name.trim(),
        kind: toolDraft.kind,
        description: toolDraft.description.trim() || undefined,
        endpoint: toolDraft.endpoint.trim() || undefined,
        transport: toolDraft.transport,
        scopes: toolDraft.scopes.split(',').map((s) => s.trim()).filter(Boolean),
      });
      setOpenTool(null);
      await load();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSavingToolEdit(false);
    }
  };

  const handleDeleteTool = async (id: string) => {
    setFormError(null);
    try {
      await apiClient.deleteTool(id);
      setOpenTool(null);
      await load();
    } catch (err) {
      setFormError((err as Error).message);
    }
  };

  const handleToggleTool = async (id: string) => {
    const tool = tools.find((t) => t.id === id);
    if (!tool) return;
    const next = !tool.enabled;
    try {
      await apiClient.setToolEnabled(id, next);
      setTools((prev) => prev.map((t) => (t.id === id ? { ...t, enabled: next } : t)));
      if (openTool?.id === id) setOpenTool({ ...openTool, enabled: next });
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handlePromoteSkill = async (id: string) => {
    try {
      await apiClient.setSkillStatus(id, 'approved');
      setSkills((prev) => prev.map((s) => (s.id === id ? { ...s, status: 'approved' } : s)));
      if (openSkill?.id === id) setOpenSkill({ ...openSkill, status: 'approved' });
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handleSkillStatus = async (id: string, status: string) => {
    try {
      await apiClient.setSkillStatus(id, status);
      setSkills((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s)));
      if (openSkill?.id === id) setOpenSkill({ ...openSkill, status });
    } catch (err) {
      setFormError((err as Error).message);
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
                  <Button variant="primary" size="sm" leftIcon={<Plus className="h-4 w-4" />} onClick={() => setShowRepoInfo(true)}>
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
                              <Button variant="ghost" size="sm" title="Edit" onClick={() => setShowRepoInfo(true)}>
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button variant="ghost" size="sm" title="Remove" className="text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={() => setShowRepoInfo(true)}>
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
                  <Button variant="primary" size="sm" leftIcon={<Plus className="h-4 w-4" />} onClick={() => { setFormError(null); setShowAddTool(true); }}>
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
                            No tools registered. Use <code className="text-primary-400">Add Tool</code> to register one.
                          </td>
                        </tr>
                      )}
                      {tools.map(tool => (
                        <tr key={tool.id} className="hover:bg-dashboard-card/30 transition-colors cursor-pointer" onClick={() => handleOpenTool(tool)}>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <Wrench className="h-4 w-4 text-dashboard-muted" />
                              <span className="text-sm font-medium text-primary-400 hover:underline">{tool.name}</span>
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
                          <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
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
                  <Button variant="primary" size="sm" leftIcon={<Plus className="h-4 w-4" />} onClick={() => { setFormError(null); setShowInstallSkill(true); }}>
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
                            No skills installed. Use <code className="text-primary-400">Install Skill</code> to add one.
                          </td>
                        </tr>
                      )}
                      {skills.map(skill => (
                        <tr key={skill.id} className="hover:bg-dashboard-card/30 transition-colors cursor-pointer" onClick={() => { setOpenSkill(skill); setFormError(null); }}>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <Code className="h-4 w-4 text-primary-400" />
                              <span className="text-sm font-medium text-primary-400 hover:underline">{skill.name}</span>
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
                          <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
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
                              <Button variant="ghost" size="sm" title="Configure" onClick={() => { setOpenSkill(skill); setFormError(null); }}>
                                <Settings className="h-4 w-4" />
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

      {/* Add Tool Modal */}
      {showAddTool && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" onClick={() => !savingTool && setShowAddTool(false)}>
          <div
            className="w-full max-w-lg bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-dashboard-border">
              <h2 className="text-lg font-semibold text-dashboard-text">Add Tool</h2>
              <button
                onClick={() => !savingTool && setShowAddTool(false)}
                className="text-dashboard-muted hover:text-dashboard-text p-1 rounded-lg hover:bg-dashboard-muted/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={(e) => { e.preventDefault(); void handleAddTool(); }} className="p-6 space-y-4">
              <Input
                label="Name"
                placeholder="e.g. artifact-inspect"
                value={toolForm.name}
                onChange={(e) => setToolForm((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
              <Select
                label="Kind"
                value={toolForm.kind}
                onChange={(e) => setToolForm((prev) => ({ ...prev, kind: e.target.value }))}
              >
                {['http', 'read', 'write', 'search', 'deploy', 'test'].map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </Select>
              <Input
                label="Description"
                placeholder="What does this tool do?"
                value={toolForm.description}
                onChange={(e) => setToolForm((prev) => ({ ...prev, description: e.target.value }))}
              />
              <Input
                label="Endpoint"
                placeholder="http://service:port/path"
                value={toolForm.endpoint}
                onChange={(e) => setToolForm((prev) => ({ ...prev, endpoint: e.target.value }))}
              />
              <Select
                label="Transport"
                value={toolForm.transport}
                onChange={(e) => setToolForm((prev) => ({ ...prev, transport: e.target.value }))}
              >
                {['http', 'mcp', 'stdio'].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </Select>
              <Input
                label="Scopes (comma-separated)"
                placeholder="artifacts:read, repo:read"
                value={toolForm.scopes}
                onChange={(e) => setToolForm((prev) => ({ ...prev, scopes: e.target.value }))}
              />
              {formError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-sm text-red-400">{formError}</p>
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <Button type="button" variant="secondary" onClick={() => setShowAddTool(false)} disabled={savingTool}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" disabled={savingTool}>
                  {savingTool ? 'Registering…' : 'Add Tool'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Install Skill Modal */}
      {showInstallSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" onClick={() => !savingSkill && setShowInstallSkill(false)}>
          <div
            className="w-full max-w-lg bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-dashboard-border">
              <h2 className="text-lg font-semibold text-dashboard-text">Install Skill</h2>
              <button
                onClick={() => !savingSkill && setShowInstallSkill(false)}
                className="text-dashboard-muted hover:text-dashboard-text p-1 rounded-lg hover:bg-dashboard-muted/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={(e) => { e.preventDefault(); void handleInstallSkill(); }} className="p-6 space-y-4">
              <Input
                label="Name"
                placeholder="e.g. ci-repair"
                value={skillForm.name}
                onChange={(e) => setSkillForm((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
              <Input
                label="Path"
                placeholder="skills/ci-repair"
                value={skillForm.path}
                onChange={(e) => setSkillForm((prev) => ({ ...prev, path: e.target.value }))}
                required
              />
              <Input
                label="Git Repository"
                placeholder="local://defaults"
                value={skillForm.gitRepository}
                onChange={(e) => setSkillForm((prev) => ({ ...prev, gitRepository: e.target.value }))}
                required
              />
              <Input
                label="Version"
                placeholder="1.0.0"
                value={skillForm.version}
                onChange={(e) => setSkillForm((prev) => ({ ...prev, version: e.target.value }))}
              />
              <Input
                label="Description"
                placeholder="What does this skill do?"
                value={skillForm.description}
                onChange={(e) => setSkillForm((prev) => ({ ...prev, description: e.target.value }))}
              />
              {formError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-sm text-red-400">{formError}</p>
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <Button type="button" variant="secondary" onClick={() => setShowInstallSkill(false)} disabled={savingSkill}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" disabled={savingSkill}>
                  {savingSkill ? 'Installing…' : 'Install Skill'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tool Detail Modal */}
      {openTool && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" onClick={() => !savingToolEdit && setOpenTool(null)}>
          <div
            className="w-full max-w-lg bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-dashboard-border">
              <h2 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                <Wrench className="h-5 w-5 text-primary-400" />
                {openTool.name}
              </h2>
              <button
                onClick={() => !savingToolEdit && setOpenTool(null)}
                className="text-dashboard-muted hover:text-dashboard-text p-1 rounded-lg hover:bg-dashboard-muted/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="px-6 py-3 border-b border-dashboard-border/50 flex items-center gap-2 text-xs text-dashboard-muted">
              <Badge variant={openTool.enabled ? 'success' : 'default'}>
                {openTool.enabled ? 'Enabled' : 'Disabled'}
              </Badge>
              {openTool.transport && <span>transport: {openTool.transport}</span>}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); void handleSaveTool(); }} className="p-6 space-y-4">
              <Input
                label="Name"
                value={toolDraft.name}
                onChange={(e) => setToolDraft((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
              <Select
                label="Kind"
                value={toolDraft.kind}
                onChange={(e) => setToolDraft((prev) => ({ ...prev, kind: e.target.value }))}
              >
                {['http', 'read', 'write', 'search', 'deploy', 'test'].map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </Select>
              <Input
                label="Description"
                value={toolDraft.description}
                onChange={(e) => setToolDraft((prev) => ({ ...prev, description: e.target.value }))}
              />
              <Input
                label="Endpoint"
                value={toolDraft.endpoint}
                onChange={(e) => setToolDraft((prev) => ({ ...prev, endpoint: e.target.value }))}
              />
              <Select
                label="Transport"
                value={toolDraft.transport}
                onChange={(e) => setToolDraft((prev) => ({ ...prev, transport: e.target.value }))}
              >
                {['http', 'mcp', 'stdio'].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </Select>
              <Input
                label="Scopes (comma-separated)"
                value={toolDraft.scopes}
                onChange={(e) => setToolDraft((prev) => ({ ...prev, scopes: e.target.value }))}
              />
              {formError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-sm text-red-400">{formError}</p>
                </div>
              )}
              <div className="flex justify-between gap-3 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                  onClick={() => void handleDeleteTool(openTool.id)}
                  disabled={savingToolEdit}
                >
                  <Trash2 className="h-4 w-4 mr-1" /> Delete
                </Button>
                <div className="flex justify-end gap-3">
                  <Button type="button" variant="secondary" onClick={() => setOpenTool(null)} disabled={savingToolEdit}>
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={savingToolEdit}>
                    {savingToolEdit ? 'Saving…' : 'Save Changes'}
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Skill Detail Modal */}
      {openSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" onClick={() => setOpenSkill(null)}>
          <div
            className="w-full max-w-lg bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-dashboard-border">
              <h2 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                <Code className="h-5 w-5 text-primary-400" />
                {openSkill.name}
              </h2>
              <button
                onClick={() => setOpenSkill(null)}
                className="text-dashboard-muted hover:text-dashboard-text p-1 rounded-lg hover:bg-dashboard-muted/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wider mb-1">Version</p>
                  <p className="text-dashboard-text">{openSkill.version}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wider mb-1">Status</p>
                  <Badge variant={getStatusColor(openSkill.status)}>{openSkill.status}</Badge>
                </div>
              </div>
              <div>
                <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wider mb-1">Digest</p>
                <p className="text-xs text-dashboard-text-secondary font-mono break-all">{openSkill.digest}</p>
              </div>
              {openSkill.description && (
                <div>
                  <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wider mb-1">Description</p>
                  <p className="text-sm text-dashboard-text">{openSkill.description}</p>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wider mb-1">Change Status</p>
                <Select
                  value={openSkill.status}
                  onChange={(e) => void handleSkillStatus(openSkill.id, e.target.value)}
                  disabled={openSkill.status === 'published'}
                >
                  {['draft', 'linted', 'sandbox-tested', 'evaluated', 'approved', 'published', 'deprecated'].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </Select>
              </div>
              {formError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-sm text-red-400">{formError}</p>
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <Button variant="secondary" onClick={() => setOpenSkill(null)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Repository Info Modal */}
      {showRepoInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" onClick={() => setShowRepoInfo(false)}>
          <div
            className="w-full max-w-md bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-dashboard-border">
              <h2 className="text-lg font-semibold text-dashboard-text">Repositories</h2>
              <button
                onClick={() => setShowRepoInfo(false)}
                className="text-dashboard-muted hover:text-dashboard-text p-1 rounded-lg hover:bg-dashboard-muted/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6 space-y-3 text-sm text-dashboard-text">
              <p>
                Repositories are provisioned by the DevFoundry installer and attached to the project
                at registration time — the first-release API does not expose repository
                create/edit/delete endpoints.
              </p>
              <p className="text-dashboard-muted">
                To attach a repository, use the CLI: <code className="text-primary-400">devfoundry project create</code>
              </p>
              <div className="flex justify-end pt-2">
                <Button variant="secondary" onClick={() => setShowRepoInfo(false)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
