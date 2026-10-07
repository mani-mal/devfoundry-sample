class DevFoundryConsole {
  constructor() {
    this.socket = null;
    this.currentTab = 'tasks';
    this.tasks = [];
    this.connectionStatus = document.getElementById('connectionStatus');
    this.statusText = document.querySelector('.status-text');
    
    this.init();
  }

  async init() {
    this.setupEventListeners();
    this.connectWebSocket();
    this.loadInitialData();
  }

  setupEventListeners() {
    // Navigation
    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
        item.classList.add('active');
        
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        const tabName = item.dataset.tab;
        document.getElementById(`tab-${tabName}`).classList.add('active');
        
        this.currentTab = tabName;
        
        if (tabName === 'health') {
          this.refreshHealth();
        }
      });
    });

    // Task list filters
    document.getElementById('filterStatus')?.addEventListener('change', () => this.renderTasks());
    document.getElementById('filterPhase')?.addEventListener('change', () => this.renderTasks());

    // Modal controls
    document.getElementById('closeModalBtn')?.addEventListener('click', () => {
      document.getElementById('taskDetailModal').classList.remove('active');
    });

    document.getElementById('closeCreateModalBtn')?.addEventListener('click', () => {
      document.getElementById('createTaskModal').classList.remove('active');
    });

    document.getElementById('cancelCreateBtn')?.addEventListener('click', () => {
      document.getElementById('createTaskModal').classList.remove('active');
    });

    document.getElementById('cancelTaskBtn')?.addEventListener('click', () => {
      this.cancelTask();
    });

    document.getElementById('resumeTaskBtn')?.addEventListener('click', () => {
      this.resumeTask();
    });

    // Create task form
    document.getElementById('createTaskForm')?.addEventListener('submit', (e) => {
      e.preventDefault();
      this.createTask();
    });

    // Health refresh
    document.getElementById('refreshHealthBtn')?.addEventListener('click', () => {
      this.refreshHealth();
    });

    // Create task button
    document.getElementById('createTaskBtn')?.addEventListener('click', () => {
      document.getElementById('createTaskModal').classList.add('active');
    });
  }

  connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    
    this.socket.onopen = () => {
      this.connectionStatus.style.backgroundColor = 'var(--success-color)';
      this.statusText.textContent = 'Connected';
      this.subscribeToEvents();
    };

    this.socket.onclose = () => {
      this.connectionStatus.style.backgroundColor = 'var(--warning-color)';
      this.statusText.textContent = 'Disconnected';
    };

    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.connectionStatus.style.backgroundColor = 'var(--danger-color)';
      this.statusText.textContent = 'Error';
    };

    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleWebSocketMessage(data);
    };
  }

  subscribeToEvents() {
    this.socket.send(JSON.stringify({
      type: 'subscribe:tasks'
    }));
    
    this.socket.send(JSON.stringify({
      type: 'subscribe:events'
    }));
  }

  async loadInitialData() {
    await this.loadTasks();
    await this.loadHealth();
  }

  async loadTasks() {
    try {
      const statusFilter = document.getElementById('filterStatus')?.value;
      const phaseFilter = document.getElementById('filterPhase')?.value;
      
      let url = '/api/tasks?';
      if (statusFilter) url += `status=${statusFilter}&`;
      if (phaseFilter) url += `phase=${phaseFilter}&`;
      
      const response = await fetch(url);
      const data = await response.json();
      
      this.tasks = data.tasks || [];
      this.renderTasks();
    } catch (error) {
      console.error('Error loading tasks:', error);
    }
  }

  async loadHealth() {
    try {
      const response = await fetch('/api/health');
      const data = await response.json();
      
      this.renderHealth(data);
    } catch (error) {
      console.error('Error loading health:', error);
    }
  }

  async refreshHealth() {
    document.getElementById('lastRefresh').textContent = `Last refreshed: ${new Date().toLocaleTimeString()}`;
    await this.loadHealth();
  }

  renderTasks() {
    const taskList = document.getElementById('taskList');
    if (!taskList) return;

    const statusFilter = document.getElementById('filterStatus')?.value;
    const phaseFilter = document.getElementById('filterPhase')?.value;

    const filteredTasks = this.tasks.filter(task => {
      if (statusFilter && task.status !== statusFilter) return false;
      if (phaseFilter && task.phase !== phaseFilter) return false;
      return true;
    });

    taskList.innerHTML = filteredTasks.map(task => this.createTaskCard(task)).join('');

    // Add click handlers
    document.querySelectorAll('.task-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (!e.target.classList.contains('btn')) {
          const taskId = card.dataset.taskId;
          this.showTaskDetail(taskId);
        }
      });
    });
  }

  createTaskCard(task) {
    const statusClass = task.status.toLowerCase();
    const phase = task.phase;
    const timeAgo = this.timeAgo(task.createdAt);
    
    return `
      <div class="task-card" data-task-id="${task.id}">
        <div class="task-card-header">
          <div class="task-id">#${task.id.substring(0, 8)}</div>
          <span class="task-meta">
            <span class="status ${statusClass}">${task.status}</span>
            <span class="phase">${phase}</span>
          </span>
        </div>
        <div class="task-description">
          ${task.description || 'No description'}
        </div>
        <div class="task-footer">
          <span class="task-timestamp">${timeAgo}</span>
          <div class="task-actions">
            <span class="icon">🚀</span>
          </div>
        </div>
      </div>
    `;
  }

  showTaskDetail(taskId) {
    const task = this.tasks.find(t => t.id === taskId);
    if (!task) return;

    document.getElementById('modalTaskId').textContent = `Task #${taskId.substring(0, 8)}`;
    document.getElementById('modalStatus').textContent = task.status;
    document.getElementById('modalPhase').textContent = task.phase;
    document.getElementById('modalDescription').textContent = task.description || '-';
    document.getElementById('modalProject').textContent = task.projectId || '-';
    document.getElementById('modalUser').textContent = task.userId || '-';
    document.getElementById('modalCreated').textContent = new Date(task.createdAt).toLocaleString();
    document.getElementById('modalBaseCommit').textContent = task.baseCommit || '-';
    
    // Render evidence
    const evidenceList = document.getElementById('modalEvidence');
    if (task.outcome?.evidence?.length > 0) {
      evidenceList.innerHTML = task.outcome.evidence.map(e => `
        <div class="evidence-item">
          <span class="evidence-type">${e.type}</span>
          <div class="evidence-content">${e.content}</div>
          <div class="evidence-provenance">${e.timestamp}</div>
        </div>
      `).join('');
    } else {
      evidenceList.innerHTML = '<div class="empty-state">No evidence yet</div>';
    }

    document.getElementById('taskDetailModal').classList.add('active');
  }

  async createTask() {
    const description = document.getElementById('taskDescription').value;
    const projectId = document.getElementById('taskProject').value;
    const skills = Array.from(document.getElementById('taskSkills')?.selectedOptions || []).map(opt => opt.value);

    try {
      const response = await fetch('/api/tasks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-tenant-id': 'default'
        },
        body: JSON.stringify({
          description,
          projectId,
          userId: 'default-user',
          baseCommit: 'HEAD',
          targetBranch: 'main',
          skills,
          contextIds: []
        })
      });

      const task = await response.json();
      
      this.tasks.unshift(task);
      this.renderTasks();
      
      document.getElementById('createTaskModal').classList.remove('active');
      document.getElementById('taskDescription').value = '';
      
      alert('Task created successfully!');
    } catch (error) {
      console.error('Error creating task:', error);
      alert('Failed to create task');
    }
  }

  async cancelTask() {
    const modal = document.getElementById('taskDetailModal');
    const taskId = modal.querySelector('#modalTaskId').textContent.replace('#', '');
    
    try {
      await fetch(`/api/tasks/${taskId}`, {
        method: 'DELETE'
      });
      
      this.socket.send(JSON.stringify({
        type: 'task:cancel',
        taskId
      }));
      
      modal.classList.remove('active');
      this.loadTasks();
    } catch (error) {
      console.error('Error cancelling task:', error);
      alert('Failed to cancel task');
    }
  }

  async resumeTask() {
    const modal = document.getElementById('taskDetailModal');
    const taskId = modal.querySelector('#modalTaskId').textContent.replace('#', '');
    
    try {
      this.socket.send(JSON.stringify({
        type: 'task:resume',
        taskId
      }));
      
      modal.classList.remove('active');
      this.loadTasks();
    } catch (error) {
      console.error('Error resuming task:', error);
      alert('Failed to resume task');
    }
  }

  handleWebSocketMessage(data) {
    switch (data.type) {
      case 'connected':
        console.log('Connected to server');
        break;
      case 'task:created':
        this.loadTasks();
        break;
      case 'task:updated':
        this.loadTasks();
        break;
      case 'task:cancelled':
        this.loadTasks();
        break;
      case 'task:resumed':
        this.loadTasks();
        break;
      case 'evidence:added':
        this.loadTasks();
        break;
    }
  }

  renderHealth(data) {
    const serviceStatus = document.getElementById('serviceStatus');
    if (serviceStatus) {
      serviceStatus.innerHTML = Object.entries(data.services).map(([name, status]) => `
        <div class="service-item">
          <div class="service-name">${name}</div>
          <div class="service-dot ${status.status === 'healthy' ? '' : 'unhealthy'}"></div>
          <div class="service-status-text">${status.status}</div>
        </div>
      `).join('');
    }

    // Update resource metrics
    const resources = data.resources || {};
    
    const cpuUsage = resources.cpu?.usage || 0;
    document.getElementById('cpuUsage').style.width = `${cpuUsage}%`;
    document.getElementById('cpuValue').textContent = `${cpuUsage}%`;

    const memoryUsage = resources.memory?.usage || 0;
    document.getElementById('memoryUsage').style.width = `${memoryUsage}%`;
    document.getElementById('memoryValue').textContent = `${memoryUsage} GB`;

    const diskUsage = resources.disk?.usage || 0;
    document.getElementById('diskUsage').style.width = `${diskUsage}%`;
    document.getElementById('diskValue').textContent = `${diskUsage} GB`;

    // Update context status
    const lastSync = resources.lastSync || 'Never';
    const statusValue = document.getElementById('lastSync');
    if (statusValue) {
      statusValue.textContent = lastSync;
    }
  }

  timeAgo(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return 'Just now';
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  new DevFoundryConsole();
});
