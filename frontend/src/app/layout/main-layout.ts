import {isPlatformBrowser} from '@angular/common';
import {Component, computed, inject, OnDestroy, OnInit, PLATFORM_ID, signal} from '@angular/core';
import {Router, RouterLink, RouterLinkActive, RouterOutlet} from '@angular/router';
import {MatIconModule} from '@angular/material/icon';
import {FormsModule} from '@angular/forms';

import {AuthService} from '../core/auth.service';
import {DataService, type NotificationItem} from '../core/data.service';
import {ChatWidgetComponent} from '../features/chat/chat-widget';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  roles: Array<'pm' | 'candidate'>;
}

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatIconModule, FormsModule, ChatWidgetComponent],
  template: `
    <div class="brand-shell flex min-h-screen">
      @if (sidebarOpen()) {
        <button
          type="button"
          class="fixed inset-0 z-30 bg-[rgba(24,20,54,0.34)] md:hidden"
          (click)="sidebarOpen.set(false)"
          aria-label="Close navigation"
        ></button>
      }

      <aside
        class="brand-sidebar fixed inset-y-0 left-0 z-40 flex w-[18.5rem] flex-col overflow-y-auto px-4 py-5 transition-transform duration-200 md:static md:translate-x-0"
        [class.translate-x-0]="sidebarOpen()"
        [class.-translate-x-full]="!sidebarOpen()"
      >
        <a routerLink="/dashboard/manager" class="flex items-center gap-3 rounded-[1.4rem] px-2 py-2 text-[var(--brand-ink)]">
          <span class="brand-logo-mark"><mat-icon class="text-[18px]">hub</mat-icon></span>
          <div>
            <p class="font-['Space_Grotesk'] text-lg font-bold tracking-tight">TalentOS</p>
            <p class="text-xs text-[var(--brand-copy-soft)]">Hiring workspace</p>
          </div>
        </a>

        <div class="surface-card mt-6 p-4">
          <p class="eyebrow">Workspace</p>
          <div class="mt-3 flex items-center gap-3">
            <div class="h-12 w-12 overflow-hidden rounded-2xl bg-[rgba(166,37,104,0.08)]">
              @if (authService.currentUser()?.avatar) {
                <img [src]="authService.currentUser()?.avatar" alt="" class="h-full w-full object-cover" />
              } @else {
                <div class="flex h-full w-full items-center justify-center bg-gradient-to-br from-primary-500 to-primary-700 text-sm font-bold text-white">
                  {{ (authService.currentUser()?.name ?? 'U').charAt(0).toUpperCase() }}
                </div>
              }
            </div>
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold text-[var(--brand-ink)]">{{ authService.currentUser()?.name }}</p>
              <p class="truncate text-xs text-[var(--brand-copy-soft)]">{{ authService.currentUser()?.email }}</p>
            </div>
          </div>
          <div class="mt-4 flex items-center justify-between rounded-[1rem] bg-[rgba(121,47,140,0.06)] px-3 py-2">
            <span class="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--brand-violet)]">Mode</span>
            <span class="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-[var(--brand-ink)]">
              {{ authService.currentUser()?.role === 'pm' ? 'Manager' : 'Candidate' }}
            </span>
          </div>
        </div>

        <nav class="mt-6 flex-1 space-y-1.5">
          @for (item of visibleNavItems(); track item.route) {
            <a
              [routerLink]="item.route"
              routerLinkActive="active-link"
              [routerLinkActiveOptions]="{exact: item.route === '/dashboard/manager'}"
              (click)="sidebarOpen.set(false)"
              class="brand-nav-link"
            >
              <mat-icon class="text-[20px]">{{ item.icon }}</mat-icon>
              <span>{{ item.label }}</span>
            </a>
          }
        </nav>

      </aside>

      <div class="flex min-w-0 flex-1 flex-col">
        <header class="sticky top-0 z-20 px-4 pb-2 pt-4 lg:px-6">
          <div class="surface-card flex flex-wrap items-center gap-3 px-4 py-3 lg:px-5">
            <button
              type="button"
              (click)="toggleSidebar()"
              class="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--brand-line)] bg-white text-[var(--brand-ink)] md:hidden"
            >
              <mat-icon>{{ sidebarOpen() ? 'close' : 'menu' }}</mat-icon>
            </button>

            <div class="min-w-0 flex-1">
              <p class="eyebrow">{{ authService.currentUser()?.role === 'pm' ? 'Talent Command' : 'Candidate Workspace' }}</p>
              <p class="truncate font-['Space_Grotesk'] text-lg font-bold text-[var(--brand-ink)]">
                {{ authService.currentUser()?.role === 'pm' ? 'Manage roles, ranking, and interviews' : 'Book your slot and complete assessment' }}
              </p>
            </div>

            @if (authService.currentUser()?.role === 'pm') {
              <div class="relative hidden min-w-[18rem] max-w-md flex-1 md:flex">
                <mat-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--brand-copy-soft)] text-[18px]">search</mat-icon>
                <input
                  type="text"
                  [(ngModel)]="searchQuery"
                  (keyup.enter)="runGlobalSearch()"
                  placeholder="Search candidates, roles, signals..."
                  class="w-full rounded-2xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.04)] py-3 pl-10 pr-4 text-sm text-[var(--brand-ink)] outline-none focus:border-primary-500 focus:bg-white focus:ring-2 focus:ring-primary-500/15"
                />
              </div>

              <div class="relative">
                <button
                  type="button"
                  (click)="toggleNotificationCenter()"
                  class="relative inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--brand-line)] bg-white text-[var(--brand-ink)] shadow-sm"
                  aria-label="Open notifications"
                >
                  <mat-icon class="text-[20px]" [class.text-primary-600]="notificationCenterOpen()">notifications</mat-icon>
                  @if (notificationBadgeCount() > 0) {
                    <span class="absolute -right-1 -top-1 inline-flex min-h-5 min-w-5 items-center justify-center rounded-full bg-primary-600 px-1.5 text-[10px] font-bold text-white">
                      {{ notificationBadgeText() }}
                    </span>
                  }
                </button>

                @if (notificationCenterOpen()) {
                  <div class="absolute right-0 top-full z-30 mt-3 w-[22rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[1.3rem] border border-[var(--brand-line)] bg-white shadow-[0_22px_48px_rgba(52,50,91,0.2)]">
                    <div class="flex items-center justify-between border-b border-[var(--brand-line)] px-4 py-3">
                      <div>
                        <p class="eyebrow">Notifications</p>
                        <p class="text-xs text-[var(--brand-copy-soft)]">{{ visibleNotifications().length }} recent updates</p>
                      </div>
                      <button
                        type="button"
                        (click)="refreshNotifications()"
                        [disabled]="notificationsLoading()"
                        class="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-[var(--brand-line)] bg-white text-[var(--brand-copy-soft)] hover:bg-[rgba(121,47,140,0.05)] disabled:cursor-not-allowed disabled:opacity-50"
                        aria-label="Refresh notifications"
                      >
                        <mat-icon class="text-[17px]">refresh</mat-icon>
                      </button>
                    </div>

                    <div class="max-h-[20.5rem] overflow-y-auto p-2">
                      @if (notificationsLoading()) {
                        <div class="rounded-2xl border border-dashed border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-8 text-center text-sm text-[var(--brand-copy-soft)]">
                          Loading notifications...
                        </div>
                      } @else if (notificationError()) {
                        <div class="rounded-2xl border border-[rgba(180,35,24,0.18)] bg-[#fff5f5] px-4 py-4 text-sm text-[#b42318]">
                          <p>{{ notificationError() }}</p>
                          <button
                            type="button"
                            (click)="refreshNotifications()"
                            class="mt-3 rounded-xl border border-[#fecaca] bg-white px-3 py-2 text-xs font-semibold text-[#b42318]"
                          >
                            Retry
                          </button>
                        </div>
                      } @else {
                        @for (notification of visibleNotifications(); track notification.id) {
                          <div class="rounded-2xl border border-[var(--brand-line)] bg-white px-3 py-3">
                            <div class="flex items-start justify-between gap-2">
                              <p class="line-clamp-1 text-sm font-semibold text-[var(--brand-ink)]">{{ notification.subject }}</p>
                              <span class="shrink-0 rounded-full bg-[rgba(52,50,91,0.08)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--brand-ink)]">{{ notification.status }}</span>
                            </div>
                            <p class="mt-1 line-clamp-2 text-xs leading-5 text-[var(--brand-copy-soft)]">{{ notification.body }}</p>
                            @if (notificationSessionId(notification); as sessionId) {
                              <button
                                type="button"
                                (click)="openNotificationReport(sessionId)"
                                class="mt-2 rounded-xl border border-[var(--brand-line)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--brand-ink)] hover:bg-[rgba(121,47,140,0.05)]"
                              >
                                View report
                              </button>
                            }
                            <p class="mt-2 text-[11px] text-[var(--brand-copy-soft)]">{{ formatNotificationDate(notification.createdAt) }}</p>
                          </div>
                        } @empty {
                          <div class="rounded-2xl border border-dashed border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-8 text-center text-sm text-[var(--brand-copy-soft)]">
                            No notifications yet.
                          </div>
                        }
                      }
                    </div>
                  </div>
                }
              </div>
            }

            <div class="relative">
              <button
                type="button"
                (click)="toggleUserMenu()"
                class="flex items-center gap-3 rounded-2xl border border-[var(--brand-line)] bg-white px-3 py-2 text-left shadow-sm"
              >
                <div class="h-10 w-10 overflow-hidden rounded-2xl bg-[rgba(166,37,104,0.08)]">
                  @if (authService.currentUser()?.avatar) {
                    <img [src]="authService.currentUser()?.avatar" alt="" class="h-full w-full object-cover" />
                  } @else {
                    <div class="flex h-full w-full items-center justify-center bg-gradient-to-br from-primary-500 to-primary-700 text-sm font-bold text-white">
                      {{ (authService.currentUser()?.name ?? 'U').charAt(0).toUpperCase() }}
                    </div>
                  }
                </div>
                <div class="hidden sm:block">
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">{{ authService.currentUser()?.name }}</p>
                  <p class="text-xs text-[var(--brand-copy-soft)]">{{ authService.currentUser()?.role === 'pm' ? 'Hiring manager' : 'Candidate' }}</p>
                </div>
                <mat-icon class="text-[18px] text-[var(--brand-copy-soft)]">expand_more</mat-icon>
              </button>

              @if (userMenuOpen()) {
                <div class="absolute right-0 top-full mt-3 w-56 rounded-[1.4rem] border border-[var(--brand-line)] bg-white p-2 shadow-[0_20px_50px_rgba(52,50,91,0.16)]">
                  <a
                    routerLink="/settings"
                    (click)="userMenuOpen.set(false)"
                    class="flex items-center gap-3 rounded-[1rem] px-3 py-3 text-sm font-medium text-[var(--brand-ink)] hover:bg-[rgba(121,47,140,0.06)]"
                  >
                    <mat-icon class="text-[18px] text-[var(--brand-copy-soft)]">settings</mat-icon>
                    Settings
                  </a>
                  <button
                    type="button"
                    (click)="logout()"
                    class="flex w-full items-center gap-3 rounded-[1rem] px-3 py-3 text-sm font-medium text-[#b42318] hover:bg-[#fff5f5]"
                  >
                    <mat-icon class="text-[18px]">logout</mat-icon>
                    Sign out
                  </button>
                </div>
              }
            </div>
          </div>
        </header>

        <main class="min-w-0 flex-1 overflow-y-auto px-4 pb-6 pt-2 lg:px-6">
          <div class="mx-auto max-w-screen-2xl">
            <router-outlet />
          </div>
        </main>
      </div>

      <app-chat-widget />
    </div>
  `,
})
export class MainLayoutComponent implements OnInit, OnDestroy {
  authService = inject(AuthService);
  dataService = inject(DataService);
  private router = inject(Router);
  private platformId = inject(PLATFORM_ID);
  private notificationRefreshHandle: ReturnType<typeof globalThis.setInterval> | null = null;
  private readonly relevantNotificationTypes = new Set([
    'SLOT_BOOKED',
    'SLOT_CHANGED',
    'REMINDER',
    'RESULT_AVAILABLE',
    'SYSTEM_ALERT',
  ]);

  sidebarOpen = signal(false);
  userMenuOpen = signal(false);
  notificationCenterOpen = signal(false);
  notifications = signal<NotificationItem[]>([]);
  notificationsLoading = signal(false);
  notificationError = signal<string | null>(null);
  searchQuery = '';

  visibleNotifications = computed(() =>
    this.notifications()
      .filter((notification) => this.isRelevantNotification(notification))
      .slice(0, 6),
  );
  notificationBadgeCount = computed(() => this.visibleNotifications().length);
  notificationBadgeText = computed(() => {
    const count = this.notificationBadgeCount();
    if (count > 9) {
      return '9+';
    }
    return `${count}`;
  });

  private allNavItems: NavItem[] = [
    {label: 'Dashboard', icon: 'dashboard', route: '/dashboard/manager', roles: ['pm']},
    {label: 'Candidates', icon: 'people_outline', route: '/candidates', roles: ['pm']},
    {label: 'Job Roles', icon: 'work_outline', route: '/jobs', roles: ['pm']},
    {label: 'AI Insights', icon: 'auto_awesome', route: '/insights', roles: ['pm']},
    {label: 'Assessment Reports', icon: 'assignment', route: '/reports', roles: ['pm']},
    {label: 'HireAgent Chat', icon: 'smart_toy', route: '/chat', roles: ['pm']},
    {label: 'Settings', icon: 'settings', route: '/settings', roles: ['pm']},
  ];

  visibleNavItems = computed(() => {
    const role = this.authService.currentUser()?.role;
    if (!role) return [];
    return this.allNavItems.filter(item => item.roles.includes(role as 'pm' | 'candidate'));
  });

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId) || this.authService.currentUser()?.role !== 'pm') {
      return;
    }

    void this.refreshNotifications();
    this.notificationRefreshHandle = globalThis.setInterval(() => {
      void this.refreshNotifications();
    }, 45000);
  }

  ngOnDestroy(): void {
    if (this.notificationRefreshHandle !== null) {
      globalThis.clearInterval(this.notificationRefreshHandle);
      this.notificationRefreshHandle = null;
    }
  }

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }

  toggleUserMenu(): void {
    this.userMenuOpen.update((value) => !value);
    this.notificationCenterOpen.set(false);
  }

  toggleNotificationCenter(): void {
    const shouldOpen = !this.notificationCenterOpen();
    this.notificationCenterOpen.set(shouldOpen);
    this.userMenuOpen.set(false);

    if (shouldOpen) {
      void this.refreshNotifications();
    }
  }

  async refreshNotifications(): Promise<void> {
    if (this.authService.currentUser()?.role !== 'pm' || this.notificationsLoading()) {
      return;
    }

    this.notificationError.set(null);

    try {
      this.notificationsLoading.set(true);
      this.notifications.set(await this.dataService.getNotifications());
    } catch {
      this.notificationError.set(this.dataService.errorMessage() ?? 'Unable to load notifications.');
    } finally {
      this.notificationsLoading.set(false);
    }
  }

  notificationSessionId(notification: NotificationItem): string | null {
    const value = notification.metadata['assessment_session_id'];
    return typeof value === 'string' && value.trim() ? value.trim() : null;
  }

  async openNotificationReport(sessionId: string): Promise<void> {
    this.notificationCenterOpen.set(false);
    await this.router.navigate(['/reports'], {queryParams: {sessionId}});
  }

  formatNotificationDate(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }

    return parsed.toLocaleString('default', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  runGlobalSearch(): void {
    if (this.searchQuery.trim()) {
      this.router.navigate(['/candidates'], {queryParams: {q: this.searchQuery.trim()}});
    }
  }

  logout(): void {
    this.userMenuOpen.set(false);
    this.authService.logout();
  }

  private isRelevantNotification(notification: NotificationItem): boolean {
    const status = notification.status.trim().toUpperCase();
    const type = notification.notificationType.trim().toUpperCase();
    if (status === 'FAILED') {
      return false;
    }
    return this.relevantNotificationTypes.has(type);
  }
}
