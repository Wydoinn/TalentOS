import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DataService } from '../../core/data.service';

@Component({
  selector: 'app-job-roles',
  standalone: true,
  imports: [MatIconModule, RouterLink, FormsModule],
  template: `
    <div class="page-shell animate-in">
      <section class="page-hero p-6">
        <div class="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span class="brand-chip">Job Architecture</span>
            <h1 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold">Create structured JDs and manage hiring demand.</h1>
            <p class="mt-3 max-w-2xl text-sm leading-7 text-white/82">Define the role, assessment window, and ranking intent before TalentOS starts matching and inviting candidates.</p>
          </div>
          <a routerLink="/jobs/create" class="inline-flex items-center gap-2 rounded-2xl border border-white/20 bg-white/12 px-5 py-3 text-sm font-semibold text-white backdrop-blur hover:bg-white/18">
            <mat-icon class="text-[20px]">add</mat-icon>
            Create New Role
          </a>
        </div>
      </section>

      <div class="relative max-w-md">
        <mat-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[20px]">search</mat-icon>
         <input type="text"
           [ngModel]="searchQuery()"
           (ngModelChange)="searchQuery.set($event)"
               placeholder="Search roles, departments, locations, requirements"
               class="w-full rounded-xl border border-rose-200 bg-white py-2 pl-10 pr-4 text-sm outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
      </div>

      <!-- Filters -->
      <div class="flex gap-2 overflow-x-auto pb-2">
        <button (click)="setFilter('All')" [class]="filter() === 'All' ? 'whitespace-nowrap rounded-full bg-primary-600 px-4 py-2 text-sm font-semibold text-white' : 'whitespace-nowrap rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-rose-50'">All Roles</button>
        <button (click)="setFilter('Active')" [class]="filter() === 'Active' ? 'whitespace-nowrap rounded-full bg-primary-600 px-4 py-2 text-sm font-semibold text-white' : 'whitespace-nowrap rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-rose-50'">Active</button>
        <button (click)="setFilter('Draft')" [class]="filter() === 'Draft' ? 'whitespace-nowrap rounded-full bg-primary-600 px-4 py-2 text-sm font-semibold text-white' : 'whitespace-nowrap rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-rose-50'">Drafts</button>
        <button (click)="setFilter('Closed')" [class]="filter() === 'Closed' ? 'whitespace-nowrap rounded-full bg-primary-600 px-4 py-2 text-sm font-semibold text-white' : 'whitespace-nowrap rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-rose-50'">Closed</button>
      </div>

      <!-- Job Roles Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        @for (job of filteredJobs(); track job.id) {
          <div class="flex flex-col overflow-hidden rounded-[1.8rem] border border-[var(--brand-line)] bg-white shadow-[0_16px_48px_rgba(52,50,91,0.08)]">
            <div class="p-6 flex-1">
              <div class="flex justify-between items-start mb-4">
                <div>
                  <h3 class="text-lg font-semibold text-gray-900">{{ job.title }}</h3>
                  <div class="flex items-center gap-3 mt-1 text-sm text-gray-500">
                    <span class="flex items-center gap-1"><mat-icon class="text-[16px]">business</mat-icon> {{ job.department }}</span>
                    <span class="flex items-center gap-1"><mat-icon class="text-[16px]">location_on</mat-icon> {{ job.location }}</span>
                  </div>
                </div>
                <span class="inline-flex items-center gap-1 rounded-full bg-[rgba(166,37,104,0.10)] px-2.5 py-1 text-xs font-medium text-[var(--brand-berry)]">
                  {{ job.status }}
                </span>
              </div>

              <p class="text-sm text-gray-600 mb-6 line-clamp-2">
                {{ job.description }}
              </p>

              <div class="space-y-4">
                <div>
                  <h4 class="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-2">Requirements</h4>
                  <div class="flex flex-wrap gap-2">
                    @for (req of job.requirements; track req) {
                  <span class="rounded-md border border-[var(--brand-line)] bg-[rgba(121,47,140,0.04)] px-2 py-1 text-xs text-[var(--brand-violet)]">
                    {{ req }}
                  </span>
                }
              </div>
            </div>

                <div class="rounded-xl border border-[rgba(166,37,104,0.12)] bg-[rgba(121,47,140,0.04)] p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h4 class="text-sm font-semibold text-gray-900 flex items-center gap-2">
                      <mat-icon class="text-primary-500 text-[18px]">auto_awesome</mat-icon>
                      Top AI Matches
                    </h4>
                    <span class="text-xs font-medium text-primary-600">{{ job.candidatesCount }} Total</span>
                  </div>
                  @if (job.candidatesCount > 0) {
                    <p class="text-xs text-gray-600">
                      Ranked candidates are available for this role. Open "View Candidates" to review details.
                    </p>
                  } @else {
                    <p class="text-xs text-gray-600">
                      No ranked candidates yet.
                    </p>
                  }
                </div>
              </div>
            </div>
            <div class="flex items-center justify-between border-t border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-6 py-4">
              <span class="text-xs text-gray-500">Posted {{ job.postedAt }}</span>
              <div class="flex gap-2">
                <button
                  (click)="deleteJob(job.id)"
                  [disabled]="deletingJobId() === job.id"
                  class="text-sm font-medium text-red-600 hover:text-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {{ deletingJobId() === job.id ? 'Deleting...' : 'Delete' }}
                </button>
                <a [routerLink]="['/jobs', job.id, 'candidates']" class="text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors">View Candidates</a>
              </div>
            </div>
          </div>
        }
      </div>
    </div>
  `
})
export class JobRolesComponent implements OnInit {
  dataService = inject(DataService);
  route = inject(ActivatedRoute);
  filter = signal('All');
  searchQuery = signal('');
  deletingJobId = signal<string | null>(null);

  ngOnInit(): void {
    void this.initialize();
  }

  private async initialize(): Promise<void> {
    const query = this.route.snapshot.queryParamMap.get('q');
    if (query) {
      this.searchQuery.set(query);
    }

    await this.dataService.loadJobs();
    await this.dataService.refreshCandidates();
  }

  filteredJobs = computed(() => {
    const currentFilter = this.filter();
    const query = this.searchQuery().trim().toLowerCase();
    const jobs = this.dataService.jobs();

    return jobs.filter(job => {
      const statusMatch = currentFilter === 'All' || job.status === currentFilter;
      const queryMatch = !query
        || job.title.toLowerCase().includes(query)
        || job.department.toLowerCase().includes(query)
        || job.location.toLowerCase().includes(query)
        || job.requirements.some((req) => req.toLowerCase().includes(query));

      return statusMatch && queryMatch;
    });
  });

  setFilter(newFilter: string) {
    this.filter.set(newFilter);
  }

  async deleteJob(jobId: string): Promise<void> {
    if (this.deletingJobId()) {
      return;
    }

    if (!confirm('Delete this job role? This action cannot be undone.')) {
      return;
    }

    this.deletingJobId.set(jobId);
    try {
      await this.dataService.deleteJob(jobId);
    } finally {
      this.deletingJobId.set(null);
    }
  }
}
