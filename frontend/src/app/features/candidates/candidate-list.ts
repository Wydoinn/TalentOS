import {Component, computed, inject, OnInit, signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MatIconModule} from '@angular/material/icon';
import {ActivatedRoute, RouterLink} from '@angular/router';

import {DataService} from '../../core/data.service';

@Component({
  selector: 'app-candidate-list',
  standalone: true,
  imports: [MatIconModule, RouterLink, FormsModule],
  template: `
    <div class="page-shell animate-in">
      <section class="page-hero p-6">
        <div class="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span class="brand-chip">Talent Review</span>
            <h1 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold">Review ranked candidates and drive the shortlist forward.</h1>
            <p class="mt-3 max-w-2xl text-sm leading-7 text-white/82">Search by skill, inspect AI match scores, and move candidates into interview decisions with the manager workflow.</p>
          </div>
        </div>
      </section>

      <div class="flex w-full flex-wrap items-center gap-3 sm:w-auto sm:flex-nowrap">
        <div class="relative w-full sm:w-64">
          <mat-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[20px]">search</mat-icon>
          <input
            type="text"
            placeholder="Search candidates..."
            [ngModel]="searchQuery()"
            (ngModelChange)="searchQuery.set($event)"
            class="w-full rounded-xl border border-rose-200 bg-white py-2 pl-10 pr-4 text-sm outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
          />
        </div>
        <select [ngModel]="sourceFilter()" (ngModelChange)="sourceFilter.set($event)" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-rose-50 sm:w-auto">
          <option value="all">All Sources</option>
          <option value="internal">Internal</option>
          <option value="external">External</option>
        </select>
        <select [ngModel]="statusFilter()" (ngModelChange)="statusFilter.set($event)" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-rose-50 sm:w-auto">
          @for (status of availableStatuses(); track status) {
            <option [value]="status">{{ status === 'All' ? 'All Stages' : status }}</option>
          }
        </select>
      </div>

      <div class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        @for (candidate of filteredCandidates(); track candidate.id) {
          <div class="group overflow-hidden rounded-[1.8rem] border border-[var(--brand-line)] bg-white shadow-[0_16px_48px_rgba(52,50,91,0.08)] transition-shadow hover:shadow-[0_22px_58px_rgba(52,50,91,0.12)]">
            <div class="p-5">
              <div class="mb-4 flex items-start justify-between">
                <div class="flex items-center gap-3">
                  <img [src]="candidate.avatar" alt="Avatar" class="h-12 w-12 rounded-full bg-rose-50" />
                  <div>
                    <h3 class="font-semibold text-gray-900">{{ candidate.name }}</h3>
                    <div class="mt-1 flex flex-wrap items-center gap-2">
                      <p class="text-xs text-gray-500">{{ candidate.role }}</p>
                      @if (candidate.source) {
                        <span
                          class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]"
                          [class]="candidate.source === 'internal' ? 'bg-primary-50 text-primary-700' : 'bg-rose-50 text-rose-700'"
                        >
                          {{ candidate.source }}
                        </span>
                      }
                    </div>
                  </div>
                </div>
                <button class="text-gray-400 hover:text-primary-700">
                  <mat-icon class="text-[20px]">more_vert</mat-icon>
                </button>
              </div>

              <div class="mb-5 space-y-3">
                <div class="flex items-center justify-between text-sm">
                  <span class="text-gray-500">AI Match Score</span>
                  <span class="font-semibold text-[var(--brand-berry)]">{{ candidate.matchScore }}%</span>
                </div>
                <div class="h-1.5 w-full rounded-full bg-[rgba(121,47,140,0.08)]">
                  <div class="h-1.5 rounded-full bg-gradient-to-r from-[var(--brand-red)] via-[var(--brand-berry)] to-[var(--brand-violet)]" [style.width.%]="candidate.matchScore"></div>
                </div>
              </div>

              <div class="mb-5 flex flex-wrap gap-2">
                @for (skill of candidate.skills; track skill) {
                  <span class="rounded-md border border-[var(--brand-line)] bg-[rgba(121,47,140,0.04)] px-2 py-1 text-xs text-[var(--brand-violet)]">
                    {{ skill }}
                  </span>
                }
              </div>

              <div class="flex items-center gap-2 border-t border-gray-100 pt-4">
                <a
                  [routerLink]="['/candidates', encodeCandidateId(candidate.id)]"
                  [queryParams]="candidateProfileQuery(candidate)"
                  class="flex-1 rounded-xl bg-primary-50 py-2 text-sm font-semibold text-primary-700 transition-colors hover:bg-primary-100"
                >
                  View Profile
                </a>
                <a [href]="emailLink(candidate.email)" class="rounded-xl border border-rose-200 p-2 text-rose-700 transition-colors hover:bg-rose-50">
                  <mat-icon class="text-[20px]">mail_outline</mat-icon>
                </a>
              </div>
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class CandidateListComponent implements OnInit {
  dataService = inject(DataService);
  route = inject(ActivatedRoute);

  searchQuery = signal('');
  statusFilter = signal('All');
  sourceFilter = signal('all');

  availableStatuses = computed(() => {
    const statuses = new Set(this.dataService.candidates().map((candidate) => candidate.status));
    return ['All', ...Array.from(statuses).sort()];
  });

  ngOnInit(): void {
    const query = this.route.snapshot.queryParamMap.get('q');
    if (query) {
      this.searchQuery.set(query);
    }

    void this.dataService.refreshCandidates();
  }

  filteredCandidates = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const status = this.statusFilter();
    const source = this.sourceFilter();
    const candidates = this.dataService.candidates();

    return candidates.filter((candidate) => {
      const queryMatch = !query
        || candidate.name.toLowerCase().includes(query)
        || candidate.role.toLowerCase().includes(query)
        || candidate.skills.some((skill) => skill.toLowerCase().includes(query));

      const statusMatch = status === 'All' || candidate.status === status;
      const sourceMatch = source === 'all' || candidate.source === source;
      return queryMatch && statusMatch && sourceMatch;
    });
  });

  emailLink(email: string): string {
    return email ? `mailto:${email}` : 'mailto:';
  }

  encodeCandidateId(candidateId: string): string {
    return encodeURIComponent(candidateId);
  }

  candidateProfileQuery(candidate: {jobId?: string; matchId?: string}): Record<string, string> {
    const query: Record<string, string> = {};

    if (candidate.jobId) {
      query['jobId'] = candidate.jobId;
    }
    if (candidate.matchId) {
      query['matchId'] = candidate.matchId;
    }

    return query;
  }
}
