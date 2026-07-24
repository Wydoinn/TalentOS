import {CommonModule, DatePipe} from '@angular/common';
import {Component, computed, inject, OnInit, signal} from '@angular/core';
import {MatIconModule} from '@angular/material/icon';
import {Router, RouterLink} from '@angular/router';

import {AuthService} from '../../core/auth.service';
import {DataService} from '../../core/data.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, MatIconModule, RouterLink, DatePipe],
  template: `
    <div class="page-shell animate-in">

      <!-- Welcome Banner -->
      <div class="page-hero p-6">
        <div class="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <p class="mb-1 text-sm font-medium text-white/70">{{ greeting() }}</p>
            <h1 class="font-['Space_Grotesk'] text-3xl font-bold">{{ authService.currentUser()?.name ?? 'Welcome' }}</h1>
            <p class="mt-1 text-sm text-white/74">{{ today | date:'EEEE, MMMM d, y' }}</p>
          </div>
          @if (role() === 'pm') {
            <div class="flex flex-wrap items-center gap-2">
              <a
                routerLink="/jobs/create"
                class="flex items-center gap-2 rounded-2xl border border-white/20 bg-white/12 px-5 py-2.5 text-sm font-semibold text-white backdrop-blur hover:bg-white/18"
              >
                <mat-icon class="text-[18px]">description</mat-icon>
                Create New Role
              </a>
            </div>
          }
        </div>

        @if (role() === 'pm' && actionMessage()) {
          <div class="mt-4 rounded-2xl border border-white/20 bg-white/12 px-4 py-3 text-sm text-white/90">
            {{ actionMessage() }}
          </div>
        }
      </div>

      @if (role() === 'pm') {
        <!-- KPI Cards -->
        <div class="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <div class="metric-card p-5">
            <div class="flex items-start justify-between mb-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-[rgba(203,30,75,0.08)]">
                <mat-icon class="text-[20px] text-[var(--brand-red)]">work_outline</mat-icon>
              </div>
              <span class="rounded-full bg-[rgba(203,30,75,0.08)] px-2 py-0.5 text-xs font-semibold text-[var(--brand-red)]">Live</span>
            </div>
            <p class="metric-value">{{ dataService.activeJobsCount() }}</p>
            <p class="soft-note mt-1">Open Roles</p>
          </div>

          <div class="metric-card p-5">
            <div class="flex items-start justify-between mb-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-[rgba(166,37,104,0.08)]">
                <mat-icon class="text-[20px] text-[var(--brand-berry)]">people_outline</mat-icon>
              </div>
            </div>
            <p class="metric-value">{{ dataService.totalCandidatesCount() }}</p>
            <p class="soft-note mt-1">Total Candidates</p>
          </div>

          <div class="metric-card p-5">
            <div class="flex items-start justify-between mb-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-[rgba(121,47,140,0.08)]">
                <mat-icon class="text-[20px] text-[var(--brand-violet)]">star_outline</mat-icon>
              </div>
            </div>
            <p class="metric-value">{{ dataService.shortlistedCount() }}</p>
            <p class="soft-note mt-1">Shortlisted</p>
          </div>

          <div class="metric-card p-5">
            <div class="flex items-start justify-between mb-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-[#fff1f3]">
                <mat-icon class="text-[20px] text-[#b42318]">cancel_outline</mat-icon>
              </div>
            </div>
            <p class="metric-value">{{ dataService.rejectedCount() }}</p>
            <p class="soft-note mt-1">Rejected</p>
          </div>
        </div>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">

          <!-- Top Candidates Table -->
          <div class="xl:col-span-2 table-shell">
            <div class="flex items-center justify-between border-b border-[var(--brand-line)] p-5">
              <div>
                <h2 class="section-title">Top Ranked Candidates</h2>
                <p class="soft-note mt-0.5 text-xs">Sorted by AI match score</p>
              </div>
              <a routerLink="/candidates" class="text-xs font-semibold text-primary-600 hover:underline flex items-center gap-1">
                View all <mat-icon class="text-[14px]">arrow_forward</mat-icon>
              </a>
            </div>
            @if (topCandidates().length > 0) {
              <div class="overflow-x-auto">
                <table class="min-w-full text-sm">
                  <thead class="table-head">
                    <tr>
                      <th class="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Candidate</th>
                      <th class="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Role</th>
                      <th class="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Score</th>
                      <th class="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-[var(--brand-line)]">
                    @for (candidate of topCandidates(); track candidate.id; let i = $index) {
                      <tr (click)="openCandidate(candidate.id, candidate.jobId, candidate.matchId)" class="cursor-pointer transition-colors hover:bg-[rgba(121,47,140,0.03)]">
                        <td class="px-5 py-3.5">
                          <div class="flex items-center gap-3">
                            <div class="relative">
                              <img [src]="candidate.avatar" alt="" class="w-8 h-8 rounded-full bg-[rgba(121,47,140,0.06)] object-cover" />
                              @if (i < 3) {
                                <span class="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                                  [class]="i === 0 ? 'bg-primary-700 text-white' : i === 1 ? 'bg-primary-300 text-primary-900' : 'bg-primary-500 text-white'">
                                  {{ i + 1 }}
                                </span>
                              }
                            </div>
                            <span class="font-medium text-gray-900 text-sm">{{ candidate.name }}</span>
                          </div>
                        </td>
                        <td class="px-5 py-3.5 text-[var(--brand-copy)] text-xs">{{ candidate.role }}</td>
                        <td class="px-5 py-3.5">
                          <div class="flex items-center gap-2">
                            <div class="h-2 w-full max-w-[100px] rounded-full bg-rose-100">
                              <div class="h-2 rounded-full bg-primary-600 transition-all"
                                   [style.width.%]="scoreBarWidth(candidate.matchScore)"
                              ></div>
                            </div>
                            <span class="text-xs font-semibold text-[var(--brand-ink)]">
                              {{ candidate.matchScore }}%
                            </span>
                          </div>
                        </td>
                        <td class="px-5 py-3.5">
                          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold"
                            [class]="statusClass(candidate.status)">
                            {{ candidate.status }}
                          </span>
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <div class="flex flex-col items-center justify-center py-16 text-center px-6">
                <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-50">
                  <mat-icon class="text-[28px] text-rose-300">people_outline</mat-icon>
                </div>
                <p class="text-sm font-medium text-gray-900 mb-1">No ranked candidates yet</p>
                <p class="text-xs text-gray-500 max-w-xs">Create a new role to generate a shortlist automatically, or open an existing role to review matched candidates.</p>
              </div>
            }
          </div>

          <!-- Right Column -->
          <div class="space-y-4">
            <!-- Roles Needing Attention -->
            <div class="surface-card p-5">
              <div class="flex items-center justify-between mb-4">
                <h2 class="text-base font-semibold text-gray-900">Roles to Review</h2>
                <mat-icon class="text-[20px] text-rose-500">warning_amber</mat-icon>
              </div>
              @if (jobsNeedingAttention().length > 0) {
                <div class="space-y-2">
                  @for (job of jobsNeedingAttention(); track job.id) {
                      <a [routerLink]="['/jobs', job.id, 'candidates']"
                        class="group flex cursor-pointer items-start justify-between rounded-xl border border-[var(--brand-line)] p-3 transition-all hover:border-primary-300 hover:bg-[rgba(121,47,140,0.04)]">
                      <div>
                        <p class="text-sm font-semibold text-gray-900 group-hover:text-primary-600 transition-colors">{{ job.title }}</p>
                        <p class="text-xs text-gray-500 mt-0.5">{{ job.candidatesCount }} candidates</p>
                      </div>
                      <span class="rounded-full px-2 py-0.5 text-xs font-medium"
                        [class]="job.status === 'Active' ? 'bg-[rgba(203,30,75,0.10)] text-[var(--brand-red)]' : 'bg-[rgba(52,50,91,0.10)] text-[var(--brand-ink)]'">
                        {{ job.status }}
                      </span>
                    </a>
                  }
                </div>
              } @else {
                <p class="soft-note py-6 text-center">All active roles are on track.</p>
              }
            </div>

            <!-- Quick Actions -->
            <div class="surface-card p-5">
              <h2 class="text-base font-semibold text-gray-900 mb-4">Quick Actions</h2>
              <div class="space-y-2">
                <a routerLink="/jobs/create" class="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors group cursor-pointer text-left">
                  <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50">
                    <mat-icon class="text-primary-600 text-[18px]">add_circle_outline</mat-icon>
                  </div>
                  <span class="text-sm font-medium text-gray-700 group-hover:text-primary-600 transition-colors">Create New Role</span>
                  <mat-icon class="text-gray-300 text-[16px] ml-auto">arrow_forward_ios</mat-icon>
                </a>
                <button type="button" (click)="openCandidates()" class="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors group cursor-pointer text-left">
                  <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50">
                    <mat-icon class="text-[18px] text-rose-700">manage_search</mat-icon>
                  </div>
                  <span class="text-sm font-medium text-gray-700 group-hover:text-primary-600 transition-colors">Browse Candidates</span>
                  <mat-icon class="text-gray-300 text-[16px] ml-auto">arrow_forward_ios</mat-icon>
                </button>
                <button type="button" (click)="openInsights()" class="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors group cursor-pointer text-left">
                  <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50">
                    <mat-icon class="text-[18px] text-rose-700">auto_awesome</mat-icon>
                  </div>
                  <span class="text-sm font-medium text-gray-700 group-hover:text-primary-600 transition-colors">AI Insights</span>
                  <mat-icon class="text-gray-300 text-[16px] ml-auto">arrow_forward_ios</mat-icon>
                </button>
              </div>
            </div>
          </div>
        </div>
      }

      @if (role() === 'candidate') {
        <!-- Candidate Dashboard -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div class="rounded-2xl border border-rose-100 bg-white p-6 text-center shadow-sm">
            <div class="w-12 h-12 rounded-2xl bg-primary-50 flex items-center justify-center mx-auto mb-4">
              <mat-icon class="text-primary-600">calendar_today</mat-icon>
            </div>
            <h3 class="font-semibold text-gray-900 mb-1">Book Your Slot</h3>
            <p class="text-sm text-gray-500 mb-4">Schedule your assessment interview</p>
            <a routerLink="/exam" class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors">
              <mat-icon class="text-[18px]">arrow_forward</mat-icon> Book Now
            </a>
          </div>

          <div class="rounded-2xl border border-rose-100 bg-white p-6 text-center shadow-sm">
            <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50">
              <mat-icon class="text-rose-700">assignment_turned_in</mat-icon>
            </div>
            <h3 class="font-semibold text-gray-900 mb-1">Assessment</h3>
            <p class="text-sm text-gray-500 mb-4">Take your scheduled assessment</p>
            <a routerLink="/assessment" class="inline-flex items-center gap-2 rounded-xl bg-primary-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-800">
              <mat-icon class="text-[18px]">play_arrow</mat-icon> Start
            </a>
          </div>

          <div class="sm:col-span-2 rounded-2xl border border-rose-100 bg-white p-6 text-center shadow-sm lg:col-span-1">
            <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50">
              <mat-icon class="text-rose-700">chat_bubble_outline</mat-icon>
            </div>
            <h3 class="font-semibold text-gray-900 mb-1">Ask HireAgent</h3>
            <p class="text-sm text-gray-500 mb-4">Get answers about your application</p>
            <a routerLink="/chat" class="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700">
              <mat-icon class="text-[18px]">smart_toy</mat-icon> Chat
            </a>
          </div>
        </div>
      }
    </div>
  `,
})
export class DashboardComponent implements OnInit {
  authService = inject(AuthService);
  dataService = inject(DataService);
  private router = inject(Router);

  today = new Date();
  actionMessage = signal<string | null>(null);

  role = computed(() => this.authService.currentUser()?.role);

  greeting = computed(() => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  });

  topCandidates = computed(() =>
    this.dataService.candidates()
      .slice()
      .sort((a, b) => b.matchScore - a.matchScore)
      .slice(0, 5)
  );

  jobsNeedingAttention = computed(() =>
    this.dataService.jobs()
      .filter(j => j.status === 'Active')
      .slice(0, 4)
  );

  ngOnInit(): void {
    void this.initialize();
  }

  async initialize(): Promise<void> {
    await this.dataService.loadJobs();
    if (this.role() === 'pm') {
      await this.dataService.refreshCandidates();
    }
  }

  async openCandidates(): Promise<void> {
    this.actionMessage.set(null);
    await this.router.navigate(['/candidates']);
  }

  async openInsights(): Promise<void> {
    this.actionMessage.set(null);
    await this.router.navigate(['/insights']);
  }

  async openCandidate(candidateId: string, jobId?: string, matchId?: string): Promise<void> {
    const queryParams: Record<string, string> = {};
    if (jobId) {
      queryParams['jobId'] = jobId;
    }
    if (matchId) {
      queryParams['matchId'] = matchId;
    }

    await this.router.navigate(['/candidates', encodeURIComponent(candidateId)], {
      queryParams,
    });
  }

  statusClass(status: string): string {
    const map: Record<string, string> = {
      'Hired': 'bg-[rgba(166,37,104,0.12)] text-[var(--brand-berry)]',
      'Shortlisted': 'bg-[rgba(203,30,75,0.10)] text-[var(--brand-red)]',
      'Interview': 'bg-[rgba(121,47,140,0.10)] text-[var(--brand-violet)]',
      'Screening': 'bg-[rgba(52,50,91,0.10)] text-[var(--brand-ink)]',
      'Rejected': 'bg-[#fff1f3] text-[#b42318]',
      'Applied': 'bg-[rgba(52,50,91,0.10)] text-[var(--brand-ink)]',
    };
    return map[status] ?? 'bg-[rgba(52,50,91,0.10)] text-[var(--brand-ink)]';
  }

  scoreBarWidth(score: number): number {
    if (!Number.isFinite(score)) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round(score)));
  }
}
