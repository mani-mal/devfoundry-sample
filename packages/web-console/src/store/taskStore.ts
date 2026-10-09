import { create } from 'zustand';
import type { Task } from '../types';

interface TaskFilters {
  phase: string | null;
  status: string | null;
  search: string;
}

interface TaskStore {
  tasks: Task[];
  activeTask: Task | null;
  filters: TaskFilters;
  setTasks: (tasks: Task[]) => void;
  setActiveTask: (task: Task | null) => void;
  setFilters: (filters: Partial<TaskFilters>) => void;
  addTask: (task: Task) => void;
  updateTask: (task: Task) => void;
  removeTask: (taskId: string) => void;
}

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: [],
  activeTask: null,
  filters: {
    phase: null,
    status: null,
    search: '',
  },
  setTasks: (tasks: Task[]) => set({ tasks }),
  setActiveTask: (activeTask: Task | null) => set({ activeTask }),
  setFilters: (filters: Partial<TaskFilters>) => set((state) => ({
    filters: { ...state.filters, ...filters },
  })),
  addTask: (task: Task) => set((state) => ({ tasks: [task, ...state.tasks] })),
  updateTask: (updatedTask: Task) => set((state) => ({
    tasks: state.tasks.map((t: Task) => (t.id === updatedTask.id ? updatedTask : t)),
    activeTask: state.activeTask?.id === updatedTask.id ? updatedTask : state.activeTask,
  })),
  removeTask: (taskId: string) => set((state) => ({
    tasks: state.tasks.filter((t: Task) => t.id !== taskId),
    activeTask: state.activeTask?.id === taskId ? null : state.activeTask,
  })),
}));
