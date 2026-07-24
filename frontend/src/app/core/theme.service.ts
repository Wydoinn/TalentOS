import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  isDarkMode = signal<boolean>(false);

  constructor() {
    if (typeof window !== 'undefined') {
      this.applyLightTheme();
    }
  }

  toggleTheme() {
    this.applyLightTheme();
  }

  private applyLightTheme() {
    this.isDarkMode.set(false);
    if (typeof document !== 'undefined') {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }
}
