import {Component, inject, signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MatIconModule} from '@angular/material/icon';

import {AuthService} from '../../core/auth.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [MatIconModule, FormsModule],
  template: `
    <div class="page-shell animate-in">
      <section class="page-hero p-6">
        <div class="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span class="brand-chip">Account Settings</span>
            <h1 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold">Manage your manager profile.</h1>
            <p class="mt-3 max-w-2xl text-sm leading-7 text-white/82">
              Update the basics here. Assessment reports and candidate outcomes now live in their own dedicated reports workspace.
            </p>
          </div>
          <div class="glass-panel px-4 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.16em] text-white/72">Workspace Role</p>
            <p class="mt-2 text-lg font-semibold text-white">Hiring Manager</p>
            <p class="mt-1 text-xs text-white/74">{{ authService.currentUser()?.email }}</p>
          </div>
        </div>
      </section>

      <section class="max-w-3xl">
        <div class="surface-card p-6">
          <p class="eyebrow">Profile</p>
          <h2 class="section-title mt-2">Account details</h2>

          <form class="mt-5 space-y-5" (ngSubmit)="onSubmit()">
            <div>
              <label for="name" class="mb-2 block text-sm font-medium text-[var(--brand-ink)]">Full Name</label>
              <input
                id="name"
                type="text"
                name="name"
                [(ngModel)]="profile.name"
                class="w-full rounded-2xl border border-[var(--brand-line)] bg-white px-4 py-3 text-sm text-[var(--brand-ink)] outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-500/15"
              />
            </div>

            <div>
              <label for="email" class="mb-2 block text-sm font-medium text-[var(--brand-ink)]">Email Address</label>
              <input
                id="email"
                type="email"
                name="email"
                [(ngModel)]="profile.email"
                disabled
                class="w-full rounded-2xl border border-[var(--brand-line)] bg-slate-100 px-4 py-3 text-sm text-slate-500"
              />
            </div>

            @if (saveMessage()) {
              <div class="rounded-2xl border border-[rgba(166,37,104,0.16)] bg-[rgba(166,37,104,0.07)] px-4 py-3 text-sm text-[var(--brand-berry)]">
                {{ saveMessage() }}
              </div>
            }

            <button type="submit" class="rounded-2xl bg-gradient-to-r from-primary-500 via-primary-600 to-primary-700 px-5 py-3 text-sm font-semibold text-white shadow-[0_18px_36px_rgba(166,37,104,0.22)]">
              Save Changes
            </button>
          </form>
        </div>
      </section>
    </div>
  `,
})
export class SettingsComponent {
  authService = inject(AuthService);

  private readonly profileStoragePrefix = 'talentos.profile.';
  saveMessage = signal<string | null>(null);

  profile = {
    name: this.authService.currentUser()?.name || '',
    email: this.authService.currentUser()?.email || '',
  };

  constructor() {
    this.loadProfile();
  }

  onSubmit(): void {
    this.saveMessage.set(null);
    this.authService.updateCurrentUserName(this.profile.name);
    this.persistProfile();
    this.saveMessage.set('Profile settings saved.');
  }

  private profileStorageKey(): string | null {
    const userId = this.authService.currentUser()?.id;
    return userId ? `${this.profileStoragePrefix}${userId}` : null;
  }

  private loadProfile(): void {
    if (typeof localStorage === 'undefined') {
      return;
    }

    const key = this.profileStorageKey();
    if (!key) {
      return;
    }

    const stored = localStorage.getItem(key);
    if (!stored) {
      return;
    }

    try {
      const parsed = JSON.parse(stored) as Partial<typeof this.profile>;
      this.profile = {
        ...this.profile,
        ...parsed,
        email: this.authService.currentUser()?.email || this.profile.email,
      };
    } catch {
      // Ignore malformed profile entries.
    }
  }

  private persistProfile(): void {
    if (typeof localStorage === 'undefined') {
      return;
    }

    const key = this.profileStorageKey();
    if (!key) {
      return;
    }

    localStorage.setItem(
      key,
      JSON.stringify({
        name: this.profile.name,
      }),
    );
  }
}
