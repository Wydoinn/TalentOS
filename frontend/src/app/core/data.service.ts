import {HttpClient} from '@angular/common/http';
import {Injectable, computed, effect, inject, signal} from '@angular/core';
import {firstValueFrom} from 'rxjs';

import {AuthService} from './auth.service';

export interface Job {
  id: string;
  managerId: string;
  title: string;
  department: string;
  location: string;
  employmentType?: string;
  seniority?: string;
  status: 'Active' | 'Draft' | 'Closed';
  description: string;
  requirements: string[];
  candidatesCount: number;
  postedAt: string;
  assessmentStartAt?: string;
  assessmentEndAt?: string;
  assessmentTimezone?: string;
  assessmentSlotMinutes?: number;
  questionBlueprint?: QuestionBlueprintItem[];
}

export interface QuestionBlueprintItem {
  stage: string;
  count: number;
}

export interface Candidate {
  id: string;
  managerId: string;
  name: string;
  role: string;
  matchScore: number;
  source?: 'internal' | 'external' | null;
  status: 'Applied' | 'Screening' | 'Shortlisted' | 'Interview' | 'Offer' | 'Rejected' | 'Hired';
  appliedAt: string;
  email: string;
  phone: string;
  experience: string;
  education: string;
  skills: string[];
  avatar: string;
  jobId?: string;
  matchId?: string;
}

export interface CandidateProfileAI {
  summary: string | null;
  geminiSummary: string | null;
  llmSummary: string | null;
  reasons: string[];
  suggestions: string[];
  issues: string[];
  matchedKeywords: string[];
  missingKeywords: string[];
  source: string | null;
  currentTitle: string | null;
  relativePath: string | null;
  matchExplanation: string | null;
  parsedResume: Record<string, unknown>;
  contact: Record<string, unknown>;
  experienceTimeline: Array<Record<string, unknown>>;
  projects: Array<Record<string, unknown>>;
  educationHistory: Array<Record<string, unknown>>;
  signals: Record<string, unknown>;
  sections: Record<string, unknown>;
  formattingSignals: Record<string, unknown>;
  generatedAt: string | null;
}

export interface ExamSlot {
  date: string;
  time: string;
  slotId?: string;
  timezone?: string;
  jobId?: string;
  scheduleId?: string;
  startAt?: string;
  endAt?: string;
  capacity?: number;
  reservedCount?: number;
  isActive?: boolean;
}

export interface CandidateSchedule {
  scheduleId: string;
  jobId: string;
  slotId: string;
  candidateName?: string | null;
  slotStartAt: string;
  slotEndAt: string;
  timezone: string;
  status: string;
}

export interface InterviewScheduleResult {
  id: string;
  candidateProfileId: string;
  jobId: string;
  slotId: string;
  invitationToken: string;
  status: string;
  bookedAt: string | null;
  cancelledAt: string | null;
}

export interface AssessmentQuestion {
  id: string;
  stage: string;
  prompt: string;
  rubric: Record<string, unknown>;
  source?: string | null;
  sequenceNo?: number | null;
}

export interface AssessmentQuestionResult {
  questionId?: string | null;
  prompt?: string | null;
  stage?: string | null;
  answerText?: string | null;
  answerTranscript?: string | null;
  score?: number | null;
  confidence?: number | null;
  classification?: string | null;
  transcriptionModel?: string | null;
  reasons?: string[];
}

export interface AssessmentResult {
  overallScore: number;
  decision: string;
  summary: string;
  sectionScores: Record<string, unknown>;
  reasons: string[];
  proctorSummary: string;
  terminationReason: string | null;
  flaggedEventsTimeline: Array<Record<string, unknown>>;
  questionResults: AssessmentQuestionResult[];
  generatedByModel: string | null;
}

export interface AssessmentReportSummary {
  assessmentSessionId: string;
  candidateProfileId: string;
  candidateName: string;
  candidateEmail: string;
  jobId: string;
  jobTitle: string;
  sessionStatus: string;
  reportAvailable: boolean;
  decision: string | null;
  overallScore: number | null;
  integrityScore: number | null;
  summary: string | null;
  terminationReason: string | null;
  generatedByModel: string | null;
  startedAt: string | null;
  endedAt: string | null;
  createdAt: string;
}

export interface AssessmentSessionStartResult {
  sessionId: string;
  jobId: string;
  websocketUrl: string;
  antiSpoofSessionId: string;
  status: string;
  integrityScore: number;
  terminationReason: string | null;
  questionBlueprint: QuestionBlueprintItem[];
}

export interface AntiSpoofStatus {
  status: string;
  finalDecision: string | null;
  latestResultStatus: string | null;
  latestSummary: string | null;
  trustScore: number | null;
  retryCount: number;
  nextAction: string | null;
}

export interface AntiSpoofChallenge {
  challengeId: string;
  challengeType: string;
  prompt: string;
  instructions: string[];
  expiresAt: string;
}

export interface AntiSpoofAnalysis {
  overallStatus: string;
  overallScore: number;
  summary: string;
  reasons: string[];
  retryAllowed: boolean;
  decisionReady: boolean;
  nextAction: string;
}

export interface AssessmentSpeechTranscript {
  transcript: string;
  model: string;
  durationSeconds: number | null;
}

export interface AssessmentVisionCheck {
  faceCount: number;
  gazeStatus: string;
  normalizedOffset: number | null;
  message: string | null;
}

export interface AssessmentProctorEventResponse {
  sessionStatus: string | null;
  terminationReason: string | null;
  eventCount: number;
  shouldAcknowledge: boolean;
  warningMessage: string | null;
}

export interface NotificationItem {
  id: string;
  recipientEmail: string;
  notificationType: string;
  subject: string;
  body: string;
  htmlBody: string | null;
  status: string;
  metadata: Record<string, unknown>;
  sentAt: string | null;
  createdAt: string;
}

export interface RankingOptions {
  source: 'all' | 'internal' | 'external';
  minimumAtsScore?: number | null;
  topN?: number | null;
  retrievalTopK?: number | null;
  candidatePoolSize?: number | null;
  finalTopK?: number | null;
}

type ApiJobStatus = 'ACTIVE' | 'DRAFT' | 'CLOSED';
type ApiMatchStatus = 'MATCHED' | 'SHORTLISTED' | 'INVITED' | 'REJECTED' | 'HIRED';
type ApiScheduleStatus = 'INVITED' | 'BOOKED' | 'RESCHEDULED' | 'CANCELLED' | 'COMPLETED' | 'NO_SHOW';

interface ApiRequirement {
  requirement_type: string;
  label: string;
  weight: number;
}

interface ApiJob {
  id: string;
  manager_user_id: string;
  title: string;
  department: string;
  location: string;
  employment_type: string;
  seniority: string;
  description: string;
  jd_text: string;
  assessment_start_at?: string | null;
  assessment_end_at?: string | null;
  assessment_timezone?: string | null;
  assessment_slot_minutes?: number | null;
  question_blueprint?: QuestionBlueprintItem[] | null;
  status: ApiJobStatus;
  requirements: ApiRequirement[];
  created_at: string;
  updated_at: string;
}

interface ApiCandidateMatch {
  match_id: string;
  candidate_external_id: string;
  candidate_name: string;
  candidate_email: string | null;
  source?: string | null;
  rank: number;
  final_score: number;
  ats_score: number;
  status: ApiMatchStatus;
  explanation: string;
}

interface ApiJobCandidatesResponse {
  job_id: string;
  ranking_result_id: string | null;
  report_run_id: string | null;
  candidates: ApiCandidateMatch[];
}

interface ApiCandidateProfileAIResponse {
  candidate_external_id: string;
  candidate_name: string;
  candidate_email: string | null;
  summary: string | null;
  gemini_summary: string | null;
  llm_summary: string | null;
  reasons: string[];
  suggestions: string[];
  issues: string[];
  matched_keywords: string[];
  missing_keywords: string[];
  source: string | null;
  current_title: string | null;
  relative_path: string | null;
  match_explanation: string | null;
  parsed_resume: Record<string, unknown>;
  contact: Record<string, unknown>;
  experience_timeline: Array<Record<string, unknown>>;
  projects: Array<Record<string, unknown>>;
  education: Array<Record<string, unknown>>;
  signals: Record<string, unknown>;
  sections: Record<string, unknown>;
  formatting_signals: Record<string, unknown>;
  generated_at: string | null;
}

interface ApiRankingRequest {
  source: 'all' | 'internal' | 'external';
  minimum_ats_score?: number | null;
  top_n?: number | null;
  retrieval_top_k?: number | null;
  candidate_pool_size?: number | null;
  final_top_k?: number | null;
}

interface ApiJobCreateRequest {
  title: string;
  department: string;
  location: string;
  employment_type: string;
  seniority: string;
  description: string;
  jd_text: string;
  assessment_start_at?: string;
  assessment_end_at?: string;
  assessment_timezone: string;
  assessment_slot_minutes: number;
  question_blueprint: QuestionBlueprintItem[];
  status: ApiJobStatus;
  requirements: {
    requirement_type: 'SKILL';
    label: string;
    weight: number;
  }[];
}

interface ApiJobUpdateRequest {
  title?: string;
  department?: string;
  location?: string;
  employment_type?: string;
  seniority?: string;
  description?: string;
  jd_text?: string;
  assessment_start_at?: string | null;
  assessment_end_at?: string | null;
  assessment_timezone?: string | null;
  assessment_slot_minutes?: number | null;
  question_blueprint?: QuestionBlueprintItem[];
  status?: ApiJobStatus;
  requirements?: {
    requirement_type: 'SKILL';
    label: string;
    weight: number;
  }[];
}

interface ApiScheduleSlot {
  id: string;
  job_id: string;
  start_at: string;
  end_at: string;
  timezone: string;
  capacity: number;
  reserved_count: number;
  is_active: boolean;
}

interface ApiCandidateSchedule {
  schedule_id: string;
  job_id: string;
  slot_id: string;
  candidate_name?: string | null;
  slot_start_at: string;
  slot_end_at: string;
  timezone: string;
  status: ApiScheduleStatus;
}

interface ApiInterviewScheduleResponse {
  id: string;
  candidate_profile_id: string;
  job_id: string;
  slot_id: string;
  invitation_token: string;
  status: ApiScheduleStatus;
  booked_at: string | null;
  cancelled_at: string | null;
}

interface ApiAssessmentSession {
  id: string;
  room_id: string;
  job_id: string;
  candidate_profile_id: string;
  status: string;
  anti_spoof_session_id: string | null;
  heartbeat_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  integrity_score?: number | null;
  termination_reason?: string | null;
  question_blueprint?: QuestionBlueprintItem[] | null;
}

interface ApiAssessmentJoinResponse {
  session: ApiAssessmentSession;
  websocket_url: string;
}

interface ApiAssessmentQuestionItem {
  id: string | null;
  stage: string;
  prompt: string;
  rubric: Record<string, unknown>;
  source?: string | null;
  sequence_no?: number | null;
}

interface ApiAssessmentQuestionResponse {
  questions: ApiAssessmentQuestionItem[];
}

interface ApiAssessmentReportResponse {
  assessment_session_id: string;
  technical_score: number;
  communication_score: number;
  integrity_score: number;
  coding_score: number;
  overall_score: number;
  decision: string;
  section_scores: Record<string, unknown>;
  reasons: string[];
  flagged_events_timeline: Record<string, unknown>[];
  question_results: AssessmentQuestionResult[];
  proctor_summary: string;
  termination_reason: string | null;
  summary: string;
  generated_by_model: string | null;
}

interface ApiAssessmentReportSummaryItem {
  assessment_session_id: string;
  candidate_profile_id: string;
  candidate_name: string;
  candidate_email: string;
  job_id: string;
  job_title: string;
  session_status: string;
  report_available: boolean;
  decision: string | null;
  overall_score: number | null;
  integrity_score: number | null;
  summary: string | null;
  termination_reason: string | null;
  generated_by_model: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

interface ApiAssessmentReportSummaryResponse {
  items: ApiAssessmentReportSummaryItem[];
}

interface ApiAntiSpoofLatestResult {
  overall_status?: string;
  human_readable_summary?: string;
}

interface ApiAntiSpoofStatusResponse {
  status?: string;
  final_decision?: string | null;
  retry_count?: number;
  trust_score?: number;
  next_action?: string;
  latest_result?: ApiAntiSpoofLatestResult | null;
}

interface ApiAntiSpoofChallengeResponse {
  challenge_id: string;
  challenge_type: string;
  prompt: string;
  instructions: string[];
  expires_at: string;
}

interface ApiAntiSpoofAnalysisResponse {
  overall_status: string;
  overall_score: number;
  human_readable_summary: string;
  reasons: string[];
  retry_allowed: boolean;
  decision_ready: boolean;
  next_action: string;
}

interface ApiAssessmentSpeechTranscriptResponse {
  transcript: string;
  model: string;
  duration_seconds?: number | null;
}

interface ApiAssessmentVisionCheckResponse {
  face_count?: number | null;
  gaze_status?: string | null;
  normalized_offset?: number | null;
  message?: string | null;
}

interface ApiAssessmentProctorEventResponse {
  session_status?: string | null;
  termination_reason?: string | null;
  event_count?: number | null;
  should_acknowledge?: boolean | null;
  warning_message?: string | null;
}

interface ApiNotification {
  id: string;
  recipient_email: string;
  notification_type: string;
  subject: string;
  body: string;
  html_body?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  sent_at: string | null;
  created_at: string;
}

@Injectable({
  providedIn: 'root',
})
export class DataService {
  private http = inject(HttpClient);
  private authService = inject(AuthService);

  private readonly apiBaseUrl = this.resolveOrchestrationBaseUrl();
  private readonly candidateInvitationStorageKey = 'talentos.candidate.invitationToken';
  private readonly candidateInvitationJobStorageKey = 'talentos.candidate.invitationJobId';
  private readonly candidateSlotLeadMinutes = 10;
  private readonly currentBootstrappedUserId = signal<string | null>(null);

  private allJobs = signal<Job[]>([]);
  private allCandidates = signal<Candidate[]>([]);
  private candidatesByJob = signal<Record<string, Candidate[]>>({});
  private candidateInvitationToken = signal<string | null>(null);
  private candidateInvitationJobId = signal<string | null>(null);

  loading = signal(false);
  errorMessage = signal<string | null>(null);

  // Exam State
  scheduledExam = signal<ExamSlot | null>(null);
  examCompleted = signal<boolean>(false);
  examScore = signal<number | null>(null);
  availableExamSlots = signal<ExamSlot[]>([]);
  candidateSchedules = signal<CandidateSchedule[]>([]);

  jobs = computed(() => this.allJobs());
  candidates = computed(() => this.allCandidates());

  activeJobsCount = computed(() => this.jobs().filter((job) => job.status === 'Active').length);
  totalCandidatesCount = computed(() => this.candidates().length);
  shortlistedCount = computed(() => this.candidates().filter((candidate) => ['Interview', 'Offer', 'Hired', 'Shortlisted'].includes(candidate.status)).length);
  rejectedCount = computed(() => this.candidates().filter((candidate) => candidate.status === 'Rejected').length);

  constructor() {
    effect(() => {
      const user = this.authService.currentUser();
      const isAuthenticated = this.authService.isAuthenticated();

      if (!user || !isAuthenticated) {
        this.currentBootstrappedUserId.set(null);
        this.resetState();
        return;
      }

      if (this.currentBootstrappedUserId() === user.id) {
        return;
      }

      this.currentBootstrappedUserId.set(user.id);
      void this.bootstrap();
    });
  }

  async bootstrap(): Promise<void> {
    await this.loadJobs();

    const role = this.authService.currentUser()?.role;
    if (role === 'pm') {
      await this.refreshCandidates();
      return;
    }

    if (role === 'candidate') {
      await this.loadCandidateInvitationToken();
      await this.loadAvailableSlots(this.candidateInvitationJobId() ?? undefined);
      await this.loadCandidateSchedules();
    }
  }

  setCandidateInvitationToken(invitationToken: string | null): void {
    const normalized = invitationToken?.trim() ?? '';
    const token = normalized.length > 0 ? normalized : null;

    this.candidateInvitationToken.set(token);

    if (typeof localStorage === 'undefined') {
      return;
    }

    if (token) {
      localStorage.setItem(this.candidateInvitationStorageKey, token);
      return;
    }

    localStorage.removeItem(this.candidateInvitationStorageKey);
  }

  setCandidateInvitationJobId(jobId: string | null): void {
    const normalized = jobId?.trim() ?? '';
    const value = normalized.length > 0 ? normalized : null;

    this.candidateInvitationJobId.set(value);

    if (typeof localStorage === 'undefined') {
      return;
    }

    if (value) {
      localStorage.setItem(this.candidateInvitationJobStorageKey, value);
      return;
    }

    localStorage.removeItem(this.candidateInvitationJobStorageKey);
  }

  getStoredCandidateInvitationToken(): string | null {
    const current = this.candidateInvitationToken();
    if (current) {
      return current;
    }

    if (typeof localStorage === 'undefined') {
      return null;
    }

    const persisted = localStorage.getItem(this.candidateInvitationStorageKey);
    return persisted?.trim() || null;
  }

  getStoredCandidateInvitationJobId(): string | null {
    const current = this.candidateInvitationJobId();
    if (current) {
      return current;
    }

    if (typeof localStorage === 'undefined') {
      return null;
    }

    const persisted = localStorage.getItem(this.candidateInvitationJobStorageKey);
    return persisted?.trim() || null;
  }

  async loadJobs(): Promise<void> {
    this.errorMessage.set(null);
    this.loading.set(true);

    try {
      const currentUser = this.authService.currentUser();
      const jobs = await firstValueFrom(
        this.http.get<ApiJob[]>(`${this.apiBaseUrl}/jobs`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const scopedJobs = currentUser?.role === 'pm'
        ? jobs.filter((job) => job.manager_user_id === currentUser.id)
        : jobs;

      this.allJobs.set(scopedJobs.map((job) => this.mapJob(job, this.candidatesByJob()[job.id]?.length ?? 0)));
    } catch (error) {
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to load jobs.'));
    } finally {
      this.loading.set(false);
    }
  }

  async refreshCandidates(): Promise<void> {
    this.errorMessage.set(null);

    const role = this.authService.currentUser()?.role;
    if (role !== 'pm') {
      this.allCandidates.set([]);
      return;
    }

    if (this.jobs().length === 0) {
      await this.loadJobs();
    }

    const jobs = this.jobs();
    const byJob: Record<string, Candidate[]> = {};
    const merged = new Map<string, Candidate>();

    for (const job of jobs) {
      const candidates = await this.loadJobCandidates(job.id);
      byJob[job.id] = candidates;

      for (const candidate of candidates) {
        const existing = merged.get(candidate.id);
        if (!existing || candidate.matchScore > existing.matchScore) {
          merged.set(candidate.id, candidate);
        }
      }
    }

    this.candidatesByJob.set(byJob);
    this.allCandidates.set([...merged.values()]);
    this.syncJobCandidateCounts();
  }

  async getCandidateById(
    candidateId: string,
    options: {jobId?: string | null; matchId?: string | null} = {},
  ): Promise<Candidate | null> {
    const rawId = candidateId.trim();
    const normalizedId = this.normalizeCandidateId(rawId);
    const normalizedMatchId = options.matchId?.trim() || null;
    const normalizedJobId = options.jobId?.trim() || null;

    const matchesId = (candidate: Candidate): boolean =>
      candidate.id === normalizedId || candidate.id === rawId;

    const findCandidate = (pool: Candidate[]): Candidate | null => {
      if (normalizedMatchId !== null) {
        const strictMatch = pool.find((candidate) =>
          candidate.matchId === normalizedMatchId
          && (normalizedJobId === null || candidate.jobId === normalizedJobId)
        );
        if (strictMatch) {
          return strictMatch;
        }
      }

      if (normalizedJobId !== null) {
        const scopedIdMatch = pool.find((candidate) => matchesId(candidate) && candidate.jobId === normalizedJobId);
        if (scopedIdMatch) {
          return scopedIdMatch;
        }
      }

      if (normalizedMatchId !== null) {
        const looseMatch = pool.find((candidate) => candidate.matchId === normalizedMatchId);
        if (looseMatch) {
          return looseMatch;
        }
      }

      return pool.find((candidate) => matchesId(candidate)) ?? null;
    };

    const local = findCandidate(this.allCandidates());
    if (local) {
      return local;
    }

    if (normalizedJobId) {
      if (this.jobs().length === 0) {
        await this.loadJobs();
      }

      const scopedCandidates = await this.loadJobCandidates(normalizedJobId);
      const scopedMatch = findCandidate(scopedCandidates);
      if (scopedMatch) {
        await this.refreshCandidates();
        return scopedMatch;
      }
    }

    if (this.jobs().length === 0) {
      await this.loadJobs();
    }

    for (const job of this.jobs()) {
      const jobCandidates = await this.loadJobCandidates(job.id);
      const found = findCandidate(jobCandidates);
      if (found) {
        await this.refreshCandidates();
        return found;
      }
    }

    return null;
  }

  async loadCandidateProfileAI(
    jobId: string,
    matchId: string,
    candidateExternalId?: string,
  ): Promise<CandidateProfileAI | null> {
    const normalizedCandidateExternalId = candidateExternalId?.trim() || null;

    try {
      const response = await firstValueFrom(
        this.http.get<ApiCandidateProfileAIResponse>(
          `${this.apiBaseUrl}/jobs/${jobId}/candidates/${matchId}/profile`,
          {
            headers: this.authService.getAuthHeaders(),
            params: normalizedCandidateExternalId
              ? {candidate_external_id: normalizedCandidateExternalId}
              : undefined,
          },
        ),
      );

      return {
        summary: response.summary,
        geminiSummary: response.gemini_summary,
        llmSummary: response.llm_summary,
        reasons: response.reasons ?? [],
        suggestions: response.suggestions ?? [],
        issues: response.issues ?? [],
        matchedKeywords: response.matched_keywords ?? [],
        missingKeywords: response.missing_keywords ?? [],
        source: response.source,
        currentTitle: response.current_title,
        relativePath: response.relative_path,
        matchExplanation: response.match_explanation,
        parsedResume: response.parsed_resume ?? {},
        contact: response.contact ?? {},
        experienceTimeline: response.experience_timeline ?? [],
        projects: response.projects ?? [],
        educationHistory: response.education ?? [],
        signals: response.signals ?? {},
        sections: response.sections ?? {},
        formattingSignals: response.formatting_signals ?? {},
        generatedAt: response.generated_at,
      };
    } catch (error) {
      const status = this.httpStatusCode(error);
      if (status !== 404) {
        this.errorMessage.set(this.extractErrorMessage(error, 'Unable to load candidate AI summary.'));
      }
      return null;
    }
  }

  async runRankingForActiveJobs(): Promise<void> {
    this.errorMessage.set(null);

    if (this.jobs().length === 0) {
      await this.loadJobs();
    }

    const activeJobs = this.jobs().filter((job) => job.status === 'Active');
    for (const job of activeJobs) {
      try {
        await this.rankCandidates(job.id);
      } catch {
        // Continue ranking other jobs even if one fails.
      }
    }

    await this.refreshCandidates();
  }

  async loadJobCandidates(jobId: string): Promise<Candidate[]> {
    const job = this.jobs().find((item) => item.id === jobId);
    if (!job) {
      return [];
    }

    try {
      const response = await firstValueFrom(
        this.http.get<ApiJobCandidatesResponse>(`${this.apiBaseUrl}/jobs/${jobId}/candidates`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const mapped = response.candidates
        .map((candidate) => this.mapCandidate(candidate, job))
        .sort((left, right) => {
          if (right.matchScore !== left.matchScore) {
            return right.matchScore - left.matchScore;
          }
          return left.name.localeCompare(right.name);
        });
      this.candidatesByJob.update((current) => ({
        ...current,
        [jobId]: mapped,
      }));
      this.syncJobCandidateCounts();
      return mapped;
    } catch (error) {
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to load job candidates.'));
      return [];
    }
  }

  async rankCandidates(jobId: string, options: Partial<RankingOptions> = {}): Promise<void> {
    const payload: ApiRankingRequest = {
      source: options.source ?? 'all',
      minimum_ats_score: options.minimumAtsScore ?? null,
      top_n: options.topN ?? 5,
      retrieval_top_k: options.retrievalTopK ?? null,
      candidate_pool_size: options.candidatePoolSize ?? null,
      final_top_k: options.finalTopK ?? null,
    };

    this.errorMessage.set(null);

    try {
      await firstValueFrom(
        this.http.post(`${this.apiBaseUrl}/jobs/${jobId}/rank-candidates`, payload, {
          headers: this.authService.getAuthHeaders(),
        }),
      );
      await this.loadJobCandidates(jobId);
      await this.refreshCandidates();
    } catch (error) {
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to run candidate ranking for this role.'));
      throw error;
    }
  }

  async addJob(job: Omit<Job, 'id' | 'candidatesCount' | 'postedAt' | 'managerId'>): Promise<Job> {
    const requirements = this.toRequirementInputs(job.requirements);
    const assessmentWindow = this.normalizeAssessmentWindow({
      startAt: job.assessmentStartAt,
      endAt: job.assessmentEndAt,
      timezone: job.assessmentTimezone,
      slotMinutes: job.assessmentSlotMinutes,
    });
    const payload: ApiJobCreateRequest = {
      title: job.title,
      department: job.department,
      location: job.location,
      employment_type: 'full_time',
      seniority: 'mid',
      description: job.description,
      jd_text: this.buildJdText(job.description, job.requirements),
      assessment_start_at: assessmentWindow?.startAt,
      assessment_end_at: assessmentWindow?.endAt,
      assessment_timezone: assessmentWindow?.timezone ?? (job.assessmentTimezone?.trim() || 'UTC'),
      assessment_slot_minutes: assessmentWindow?.slotMinutes ?? Math.max(5, Math.min(180, Math.trunc(job.assessmentSlotMinutes ?? 30))),
      question_blueprint: this.normalizeQuestionBlueprint(job.questionBlueprint),
      status: this.toApiJobStatus(job.status),
      requirements,
    };

    this.errorMessage.set(null);

    try {
      const created = await firstValueFrom(
        this.http.post<ApiJob>(`${this.apiBaseUrl}/jobs`, payload, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const mapped = this.mapJob(created, 0);
      this.allJobs.update((jobs) => [mapped, ...jobs]);
      return mapped;
    } catch (error) {
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to create job.'));
      throw error;
    }
  }

  async updateJob(id: string, updates: Partial<Job>): Promise<void> {
    const payload: ApiJobUpdateRequest = {};
    let existing = this.allJobs().find((job) => job.id === id);
    if (!existing) {
      await this.loadJobs();
      existing = this.allJobs().find((job) => job.id === id);
    }

    if (!existing) {
      this.errorMessage.set('Unable to find the role for update.');
      return;
    }

    if (updates.title !== undefined && updates.title !== existing.title) {
      payload.title = updates.title;
    }
    if (updates.department !== undefined && updates.department !== existing.department) {
      payload.department = updates.department;
    }
    if (updates.location !== undefined && updates.location !== existing.location) {
      payload.location = updates.location;
    }
    if (updates.employmentType !== undefined && updates.employmentType !== existing.employmentType) {
      payload.employment_type = updates.employmentType;
    }
    if (updates.seniority !== undefined && updates.seniority !== existing.seniority) {
      payload.seniority = updates.seniority;
    }
    if (updates.description !== undefined && updates.description !== existing.description) {
      payload.description = updates.description;
    }
    if (updates.status !== undefined && updates.status !== existing.status) {
      payload.status = this.toApiJobStatus(updates.status);
    }

    const requirementsChanged = updates.requirements !== undefined
      && !this.areStringArraysEqual(updates.requirements, existing.requirements);
    if (requirementsChanged) {
      payload.requirements = this.toRequirementInputs(updates.requirements ?? []);
    }

    const questionBlueprintChanged = updates.questionBlueprint !== undefined
      && !this.areQuestionBlueprintsEqual(updates.questionBlueprint, existing.questionBlueprint ?? []);
    if (questionBlueprintChanged) {
      payload.question_blueprint = this.normalizeQuestionBlueprint(updates.questionBlueprint);
    }

    const hasAssessmentStart = Object.prototype.hasOwnProperty.call(updates, 'assessmentStartAt');
    const hasAssessmentEnd = Object.prototype.hasOwnProperty.call(updates, 'assessmentEndAt');
    const hasAssessmentTimezone = Object.prototype.hasOwnProperty.call(updates, 'assessmentTimezone');
    const hasAssessmentSlotMinutes = Object.prototype.hasOwnProperty.call(updates, 'assessmentSlotMinutes');
    const windowChanged = (
      hasAssessmentStart && updates.assessmentStartAt !== existing.assessmentStartAt
    ) || (
      hasAssessmentEnd && updates.assessmentEndAt !== existing.assessmentEndAt
    ) || (
      hasAssessmentTimezone && updates.assessmentTimezone !== existing.assessmentTimezone
    ) || (
      hasAssessmentSlotMinutes && updates.assessmentSlotMinutes !== existing.assessmentSlotMinutes
    );

    const shouldRebuildJd = Boolean(payload.description !== undefined || requirementsChanged);

    if (shouldRebuildJd) {
      const mergedDescription = payload.description ?? existing.description;
      const mergedRequirements = updates.requirements ?? existing.requirements;
      payload.jd_text = this.buildJdText(mergedDescription, mergedRequirements);
    }

    if (windowChanged) {
      const hasExplicitClear = (
        hasAssessmentStart
        && hasAssessmentEnd
        && (updates.assessmentStartAt == null || updates.assessmentStartAt === '')
        && (updates.assessmentEndAt == null || updates.assessmentEndAt === '')
      );
      const normalizedWindow = hasExplicitClear
        ? null
        : this.normalizeAssessmentWindow({
          startAt: updates.assessmentStartAt ?? existing.assessmentStartAt,
          endAt: updates.assessmentEndAt ?? existing.assessmentEndAt,
          timezone: updates.assessmentTimezone ?? existing.assessmentTimezone,
          slotMinutes: updates.assessmentSlotMinutes ?? existing.assessmentSlotMinutes,
        });

      payload.assessment_start_at = normalizedWindow?.startAt ?? null;
      payload.assessment_end_at = normalizedWindow?.endAt ?? null;
      payload.assessment_timezone = normalizedWindow?.timezone
        ?? updates.assessmentTimezone
        ?? existing.assessmentTimezone
        ?? 'UTC';
      payload.assessment_slot_minutes = normalizedWindow?.slotMinutes
        ?? updates.assessmentSlotMinutes
        ?? existing.assessmentSlotMinutes
        ?? 30;
    }

    if (Object.keys(payload).length === 0) {
      return;
    }

    this.errorMessage.set(null);

    try {
      const updated = await firstValueFrom(
        this.http.put<ApiJob>(`${this.apiBaseUrl}/jobs/${id}`, payload, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const candidateCount = this.candidatesByJob()[id]?.length ?? 0;
      const mapped = this.mapJob(updated, candidateCount);
      this.allJobs.update((jobs) => jobs.map((job) => (job.id === id ? mapped : job)));
    } catch (error) {
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to update job.'));
      throw error;
    }
  }

  async deleteJob(id: string): Promise<void> {
    this.errorMessage.set(null);

    try {
      await firstValueFrom(
        this.http.delete(`${this.apiBaseUrl}/jobs/${id}`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      this.allJobs.update((jobs) => jobs.filter((job) => job.id !== id));
      this.candidatesByJob.update((byJob) => {
        const next = {...byJob};
        delete next[id];
        return next;
      });
      this.allCandidates.update((candidates) => candidates.filter((candidate) => candidate.jobId !== id));
    } catch (error) {
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to delete job.'));
      throw error;
    }
  }

  async updateCandidateStatus(id: string, status: Candidate['status']): Promise<void> {
    const target = this.allCandidates().find((candidate) => candidate.id === id);
    if (!target) {
      return;
    }

    const previousStatus = target.status;
    this.applyCandidateStatusLocally(id, status);

    if (!target.matchId || !target.jobId) {
      return;
    }

    this.errorMessage.set(null);

    try {
      const response = await firstValueFrom(
        this.http.patch<ApiCandidateMatch>(
          `${this.apiBaseUrl}/jobs/${target.jobId}/candidates/${target.matchId}/status`,
          {status: this.toApiMatchStatus(status)},
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      this.applyCandidateStatusLocally(id, this.mapCandidateStatus(response.status));
    } catch (error) {
      this.applyCandidateStatusLocally(id, previousStatus);
      const message = this.extractErrorMessage(error, 'Unable to update candidate status.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async inviteCandidate(jobId: string, candidate: {email: string; name: string; userId?: string | null}): Promise<ApiInterviewScheduleResponse> {
    this.errorMessage.set(null);

    try {
      return await firstValueFrom(
        this.http.post<ApiInterviewScheduleResponse>(
          `${this.apiBaseUrl}/schedules/${jobId}/invite`,
          {
            candidate_email: candidate.email,
            candidate_name: candidate.name,
            candidate_user_id: candidate.userId?.trim() || undefined,
          },
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to send candidate invite.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async getNotifications(): Promise<NotificationItem[]> {
    try {
      const notifications = await firstValueFrom(
        this.http.get<ApiNotification[]>(`${this.apiBaseUrl}/notifications/me`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      return notifications.map((item) => ({
        id: item.id,
        recipientEmail: item.recipient_email,
        notificationType: item.notification_type,
        subject: item.subject,
        body: item.body,
        htmlBody: item.html_body ?? null,
        status: item.status,
        metadata: item.metadata ?? {},
        sentAt: item.sent_at,
        createdAt: item.created_at,
      }));
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to load notifications.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async loadAvailableSlots(jobId?: string): Promise<void> {
    this.errorMessage.set(null);

    const role = this.authService.currentUser()?.role;
    const effectiveJobId = jobId
      ?? (role === 'candidate'
        ? (this.candidateInvitationJobId() ?? this.scheduledExam()?.jobId ?? undefined)
        : undefined);

    try {
      const suffix = effectiveJobId ? `?job_id=${encodeURIComponent(effectiveJobId)}` : '';
      const slots = await firstValueFrom(
        this.http.get<ApiScheduleSlot[]>(`${this.apiBaseUrl}/schedules/slots${suffix}`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const mapped = slots
        .filter((slot) => slot.is_active)
        .map((slot) => this.mapScheduleSlot(slot));

      const candidateCutoff = new Date(Date.now() + (this.candidateSlotLeadMinutes * 60 * 1000));
      const eligible = role === 'candidate'
        ? mapped.filter((slot) => {
          if (!slot.startAt) {
            return true;
          }
          const start = new Date(slot.startAt);
          return !Number.isNaN(start.getTime()) && start > candidateCutoff;
        })
        : mapped;

      if (eligible.length > 0) {
        this.availableExamSlots.set(eligible);
      } else {
        this.availableExamSlots.set([]);
      }
    } catch (error) {
      this.availableExamSlots.set([]);
      this.errorMessage.set(this.extractErrorMessage(error, 'Unable to load available exam slots.'));
    }
  }

  async createScheduleSlot(payload: {
    jobId: string;
    startAt: string;
    endAt: string;
    timezone?: string;
    capacity?: number;
  }): Promise<ExamSlot> {
    this.errorMessage.set(null);

    try {
      const slot = await firstValueFrom(
        this.http.post<ApiScheduleSlot>(
          `${this.apiBaseUrl}/schedules/slots`,
          {
            job_id: payload.jobId,
            start_at: payload.startAt,
            end_at: payload.endAt,
            timezone: payload.timezone?.trim() || 'UTC',
            capacity: Math.max(1, Math.min(20, Math.trunc(payload.capacity ?? 1))),
          },
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      return this.mapScheduleSlot(slot);
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to create schedule slot.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async scheduleExam(slot: ExamSlot): Promise<void> {
    const user = this.authService.currentUser();
    if (!user) {
      return;
    }

    const shouldBookCandidateSlot = user.role === 'candidate' && Boolean(slot.slotId);
    if (shouldBookCandidateSlot && !this.candidateInvitationToken()) {
      await this.loadCandidateInvitationToken();
    }

    if (shouldBookCandidateSlot && slot.slotId && this.candidateInvitationToken()) {
      this.errorMessage.set(null);

      try {
        const response = await firstValueFrom(
          this.http.post<ApiInterviewScheduleResponse>(
            `${this.apiBaseUrl}/schedules/book`,
            {
              invitation_token: this.candidateInvitationToken(),
              slot_id: slot.slotId,
            },
            {
              headers: this.authService.getAuthHeaders(),
            },
          ),
        );

        this.scheduledExam.set({
          ...slot,
          scheduleId: response.id,
          jobId: response.job_id,
          slotId: response.slot_id,
        });
        this.setCandidateInvitationJobId(response.job_id);
        await this.loadCandidateSchedules();
        return;
      } catch (error) {
        this.errorMessage.set(this.extractErrorMessage(error, 'Unable to book exam slot.'));
      }
    }

    if (shouldBookCandidateSlot && !this.candidateInvitationToken()) {
      this.errorMessage.set('Invitation token is missing. Open your candidate invitation link and try again.');
      return;
    }

    this.scheduledExam.set(slot);
  }

  async rescheduleCandidateSchedule(scheduleId: string, slotId: string): Promise<InterviewScheduleResult> {
    this.errorMessage.set(null);

    try {
      const response = await firstValueFrom(
        this.http.post<ApiInterviewScheduleResponse>(
          `${this.apiBaseUrl}/schedules/${encodeURIComponent(scheduleId)}/reschedule`,
          {
            slot_id: slotId,
          },
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      await this.loadCandidateSchedules();
      return this.mapInterviewSchedule(response);
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to reschedule assessment slot.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async cancelSchedule(scheduleId: string, reason: string): Promise<InterviewScheduleResult> {
    this.errorMessage.set(null);

    try {
      const response = await firstValueFrom(
        this.http.post<ApiInterviewScheduleResponse>(
          `${this.apiBaseUrl}/schedules/${encodeURIComponent(scheduleId)}/cancel`,
          {
            reason: reason.trim() || 'Cancelled by user',
          },
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      await this.loadCandidateSchedules();
      return this.mapInterviewSchedule(response);
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to cancel assessment schedule.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  completeExam(score: number): void {
    this.examCompleted.set(true);
    this.examScore.set(score);
  }

  async startAssessmentSession(): Promise<AssessmentSessionStartResult> {
    const user = this.authService.currentUser();
    if (!user?.email) {
      throw new Error('Authenticated user email is required to start an assessment.');
    }

    if (this.jobs().length === 0) {
      await this.loadJobs();
    }

    const scheduled = this.scheduledExam();
    if (user.role === 'candidate' && !scheduled?.scheduleId) {
      throw new Error('Book an assessment slot first. The assessment starts only from your emailed access link.');
    }

    const jobId = scheduled?.jobId ?? this.jobs()[0]?.id;
    if (!jobId) {
      throw new Error('No job is available for assessment.');
    }

    const createPayload: {
      job_id: string;
      candidate_email: string;
      interview_schedule_id?: string;
    } = {
      job_id: jobId,
      candidate_email: user.email,
    };

    if (scheduled?.scheduleId) {
      createPayload.interview_schedule_id = scheduled.scheduleId;
    }

    this.errorMessage.set(null);

    try {
      const created = await firstValueFrom(
        this.http.post<ApiAssessmentSession>(`${this.apiBaseUrl}/assessment/sessions`, createPayload, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      if (user.role === 'candidate' && !created.anti_spoof_session_id) {
        throw new Error('Anti-spoof verification is unavailable. Please retry in a few minutes.');
      }

      const joinResponse = await firstValueFrom(
        this.http.post<ApiAssessmentJoinResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${created.id}/join`,
          {},
          {headers: this.authService.getAuthHeaders()},
        ),
      );

      const joinedSession = joinResponse.session ?? created;

      return {
        sessionId: created.id,
        jobId,
        websocketUrl: this.buildAssessmentWebSocketUrl(joinResponse.websocket_url),
        antiSpoofSessionId: joinedSession.anti_spoof_session_id ?? '',
        status: joinedSession.status,
        integrityScore: typeof joinedSession.integrity_score === 'number' ? joinedSession.integrity_score : 0,
        terminationReason: joinedSession.termination_reason ?? null,
        questionBlueprint: this.normalizeQuestionBlueprint(joinedSession.question_blueprint),
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to start assessment session.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async loadAssessmentQuestions(sessionId: string, jobId: string): Promise<AssessmentQuestion[]> {
    const user = this.authService.currentUser();
    if (!user?.email) {
      throw new Error('Authenticated user email is required to prepare assessment questions.');
    }

    const selectedJob = this.jobs().find((job) => job.id === jobId);
    const jdContext = selectedJob
      ? this.buildJdText(selectedJob.description, selectedJob.requirements)
      : 'General software engineering role with coding, communication, and problem-solving requirements.';
    const resolvedCandidateName = this.candidateSchedules()
      .find((schedule) => schedule.candidateName?.trim())
      ?.candidateName?.trim()
      || user.name?.trim()
      || 'Candidate';
    const resumeContext = `Candidate name: ${resolvedCandidateName}. Assessment context generated from scheduled interview.`;
    const stagePlan = this.normalizeQuestionBlueprint(selectedJob?.questionBlueprint);

    try {
      const responses = await Promise.all(
        stagePlan.map(async (stageConfig, index) => {
          const priorStages = stagePlan
            .slice(0, index)
            .map((item) => item.stage);

          const response = await firstValueFrom(
            this.http.post<ApiAssessmentQuestionResponse>(
              `${this.apiBaseUrl}/assessment/sessions/${sessionId}/questions`,
              {
                stage: stageConfig.stage,
                jd_context: jdContext,
                resume_context: resumeContext,
                role_seniority: selectedJob?.seniority ?? 'mid',
                previous_answers: priorStages,
                count: stageConfig.count,
              },
              {headers: this.authService.getAuthHeaders()},
            ),
          );

          return response.questions
            .filter((question): question is ApiAssessmentQuestionItem & {id: string} => typeof question.id === 'string' && question.id.length > 0)
            .map((question) => ({
              id: question.id,
              stage: question.stage,
              prompt: question.prompt,
              rubric: question.rubric,
              source: question.source ?? null,
              sequenceNo: question.sequence_no ?? null,
            }));
        }),
      );

      return responses.flat();
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to load assessment questions.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async getAntiSpoofStatus(sessionId: string): Promise<AntiSpoofStatus> {
    try {
      const response = await firstValueFrom(
        this.http.get<ApiAntiSpoofStatusResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/anti-spoof`,
          {headers: this.authService.getAuthHeaders()},
        ),
      );

      return this.mapAntiSpoofStatus(response);
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to fetch anti-spoof verification status.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async issueAntiSpoofChallenge(sessionId: string): Promise<AntiSpoofChallenge> {
    try {
      const response = await firstValueFrom(
        this.http.post<ApiAntiSpoofChallengeResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/anti-spoof/challenge`,
          {},
          {headers: this.authService.getAuthHeaders()},
        ),
      );

      return {
        challengeId: response.challenge_id,
        challengeType: response.challenge_type,
        prompt: response.prompt,
        instructions: response.instructions ?? [],
        expiresAt: response.expires_at,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to issue anti-spoof challenge.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async analyzeAntiSpoof(sessionId: string, videoFile: File): Promise<AntiSpoofAnalysis> {
    const formData = new FormData();
    formData.append('video', videoFile, videoFile.name);

    try {
      const response = await firstValueFrom(
        this.http.post<ApiAntiSpoofAnalysisResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/anti-spoof/analyze`,
          formData,
          {headers: this.authService.getAuthHeaders()},
        ),
      );

      return {
        overallStatus: response.overall_status,
        overallScore: response.overall_score,
        summary: response.human_readable_summary,
        reasons: response.reasons ?? [],
        retryAllowed: Boolean(response.retry_allowed),
        decisionReady: Boolean(response.decision_ready),
        nextAction: response.next_action,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to complete anti-spoof analysis.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async finalizeAntiSpoof(sessionId: string): Promise<AntiSpoofStatus> {
    try {
      await firstValueFrom(
        this.http.post(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/anti-spoof/finalize`,
          {},
          {headers: this.authService.getAuthHeaders()},
        ),
      );
    } catch {
      // Finalize may return conflict when already finalized; status fetch below remains the source of truth.
    }

    return this.getAntiSpoofStatus(sessionId);
  }

  async transcribeAssessmentAnswer(sessionId: string, audioFile: File): Promise<AssessmentSpeechTranscript> {
    const formData = new FormData();
    formData.append('audio', audioFile, audioFile.name);

    try {
      const response = await firstValueFrom(
        this.http.post<ApiAssessmentSpeechTranscriptResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/transcribe`,
          formData,
          {headers: this.authService.getAuthHeaders()},
        ),
      );

      return {
        transcript: response.transcript,
        model: response.model,
        durationSeconds: typeof response.duration_seconds === 'number' ? response.duration_seconds : null,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to transcribe the spoken answer.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async analyzeAssessmentVision(sessionId: string, imageFile: File): Promise<AssessmentVisionCheck> {
    const formData = new FormData();
    formData.append('image', imageFile, imageFile.name);

    try {
      const response = await firstValueFrom(
        this.http.post<ApiAssessmentVisionCheckResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/vision-check`,
          formData,
          {headers: this.authService.getAuthHeaders()},
        ),
      );

      return {
        faceCount: Math.max(0, Number(response.face_count ?? 0)),
        gazeStatus: `${response.gaze_status ?? 'UNKNOWN'}`.toUpperCase(),
        normalizedOffset: typeof response.normalized_offset === 'number' ? response.normalized_offset : null,
        message: response.message ?? null,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to analyze the live proctoring frame.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async submitAssessmentAnswer(
    sessionId: string,
    questionId: string,
    answerText: string,
    answerTranscript: string | null = null,
    transcriptionModel: string | null = null,
  ): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/answers`,
          {
            question_id: questionId,
            answer_text: answerText,
            answer_transcript: answerTranscript,
            transcription_model: transcriptionModel,
          },
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to submit answer.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async sendAssessmentHeartbeat(sessionId: string, status = 'IN_PROGRESS'): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/heartbeat`,
          {status},
          {headers: this.authService.getAuthHeaders()},
        ),
      );
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to refresh assessment session.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async ingestProctorEvent(
    sessionId: string,
    event: {
      eventType: string;
      severity: 'INFO' | 'WARNING' | 'CRITICAL';
      payload?: Record<string, unknown>;
      eventTimestamp?: string | Date;
    },
  ): Promise<AssessmentProctorEventResponse> {
    try {
      const response = await firstValueFrom(
        this.http.post<ApiAssessmentProctorEventResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/proctor-events`,
          {
            event_type: event.eventType,
            severity: event.severity,
            event_timestamp: (event.eventTimestamp instanceof Date
              ? event.eventTimestamp.toISOString()
              : event.eventTimestamp) ?? new Date().toISOString(),
            payload: event.payload ?? {},
          },
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      return {
        sessionStatus: response.session_status ?? null,
        terminationReason: response.termination_reason ?? null,
        eventCount: Math.max(0, Number(response.event_count ?? 0)),
        shouldAcknowledge: Boolean(response.should_acknowledge),
        warningMessage: response.warning_message ?? null,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to record proctoring event.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async finishAssessmentSession(sessionId: string): Promise<AssessmentResult> {
    try {
      const report = await firstValueFrom(
        this.http.post<ApiAssessmentReportResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/finish`,
          {},
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      const roundedScore = Math.max(0, Math.min(100, Math.round(report.overall_score)));
      this.completeExam(roundedScore);

      return {
        overallScore: report.overall_score,
        decision: report.decision,
        summary: report.summary,
        sectionScores: report.section_scores ?? {},
        reasons: report.reasons ?? [],
        proctorSummary: report.proctor_summary ?? '',
        terminationReason: report.termination_reason ?? null,
        flaggedEventsTimeline: report.flagged_events_timeline ?? [],
        questionResults: (report.question_results ?? []).map((item) => this.mapAssessmentQuestionResult(item)),
        generatedByModel: report.generated_by_model ?? null,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to finalize assessment.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async getAssessmentReport(sessionId: string): Promise<AssessmentResult> {
    try {
      const report = await firstValueFrom(
        this.http.get<ApiAssessmentReportResponse>(
          `${this.apiBaseUrl}/assessment/sessions/${sessionId}/report`,
          {
            headers: this.authService.getAuthHeaders(),
          },
        ),
      );

      return {
        overallScore: report.overall_score,
        decision: report.decision,
        summary: report.summary,
        sectionScores: report.section_scores ?? {},
        reasons: report.reasons ?? [],
        proctorSummary: report.proctor_summary ?? '',
        terminationReason: report.termination_reason ?? null,
        flaggedEventsTimeline: report.flagged_events_timeline ?? [],
        questionResults: (report.question_results ?? []).map((item) => this.mapAssessmentQuestionResult(item)),
        generatedByModel: report.generated_by_model ?? null,
      };
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to load assessment report.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async getAssessmentReportSummaries(filters: {jobId?: string | null; candidateEmail?: string | null} = {}): Promise<AssessmentReportSummary[]> {
    try {
      const params: Record<string, string> = {};
      if (filters.jobId?.trim()) {
        params['job_id'] = filters.jobId.trim();
      }
      if (filters.candidateEmail?.trim()) {
        params['candidate_email'] = filters.candidateEmail.trim().toLowerCase();
      }

      const response = await firstValueFrom(
        this.http.get<ApiAssessmentReportSummaryResponse>(
          `${this.apiBaseUrl}/assessment/reports`,
          {
            headers: this.authService.getAuthHeaders(),
            params,
          },
        ),
      );

      return (response.items ?? []).map((item) => ({
        assessmentSessionId: item.assessment_session_id,
        candidateProfileId: item.candidate_profile_id,
        candidateName: item.candidate_name,
        candidateEmail: item.candidate_email,
        jobId: item.job_id,
        jobTitle: item.job_title,
        sessionStatus: item.session_status,
        reportAvailable: Boolean(item.report_available),
        decision: item.decision ?? null,
        overallScore: typeof item.overall_score === 'number' ? item.overall_score : null,
        integrityScore: typeof item.integrity_score === 'number' ? item.integrity_score : null,
        summary: item.summary ?? null,
        terminationReason: item.termination_reason ?? null,
        generatedByModel: item.generated_by_model ?? null,
        startedAt: item.started_at ?? null,
        endedAt: item.ended_at ?? null,
        createdAt: item.created_at,
      }));
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to load assessment reports.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  async loadCandidateSchedules(): Promise<CandidateSchedule[]> {
    try {
      const schedules = await firstValueFrom(
        this.http.get<ApiCandidateSchedule[]>(`${this.apiBaseUrl}/schedules/me`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const mappedSchedules = schedules.map((schedule) => ({
        scheduleId: schedule.schedule_id,
        jobId: schedule.job_id,
        slotId: schedule.slot_id,
        candidateName: schedule.candidate_name ?? null,
        slotStartAt: schedule.slot_start_at,
        slotEndAt: schedule.slot_end_at,
        timezone: schedule.timezone,
        status: schedule.status,
      }));
      this.candidateSchedules.set(mappedSchedules);
      this.scheduledExam.set(null);
      this.examCompleted.set(schedules.some((schedule) => schedule.status === 'COMPLETED'));

      const resolvedCandidateName = mappedSchedules.find((schedule) => schedule.candidateName?.trim())?.candidateName?.trim();
      if (resolvedCandidateName) {
        this.authService.updateCurrentUserName(resolvedCandidateName);
      }

      const active = schedules.find((schedule) => schedule.status === 'BOOKED' || schedule.status === 'RESCHEDULED');
      if (active) {
        const start = new Date(active.slot_start_at);
        const end = new Date(active.slot_end_at);
        this.scheduledExam.set({
          date: this.toLocalDateKey(start),
          time: start.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
          slotId: active.slot_id,
          timezone: active.timezone,
          jobId: active.job_id,
          scheduleId: active.schedule_id,
          startAt: active.slot_start_at,
          endAt: Number.isNaN(end.getTime()) ? undefined : active.slot_end_at,
        });
        this.setCandidateInvitationJobId(active.job_id);
      }

      return mappedSchedules;
    } catch {
      // Candidate schedules are optional for first-time users.
      this.candidateSchedules.set([]);
      return [];
    }
  }

  private async loadCandidateInvitationToken(): Promise<void> {
    if (typeof localStorage !== 'undefined') {
      const persisted = localStorage.getItem(this.candidateInvitationStorageKey);
      const persistedJobId = localStorage.getItem(this.candidateInvitationJobStorageKey);
      if (persisted && persisted.trim().length > 0) {
        this.candidateInvitationToken.set(persisted.trim());
        this.candidateInvitationJobId.set(persistedJobId?.trim() || null);
        return;
      }
    }

    try {
      const notifications = await firstValueFrom(
        this.http.get<ApiNotification[]>(`${this.apiBaseUrl}/notifications/me`, {
          headers: this.authService.getAuthHeaders(),
        }),
      );

      const invite = notifications.find((item) => item.notification_type === 'L0_INVITE');
      const token = invite?.metadata['invitation_token'];
      const jobId = invite?.metadata['job_id'];
      this.setCandidateInvitationToken(typeof token === 'string' ? token : null);
      this.setCandidateInvitationJobId(typeof jobId === 'string' ? jobId : null);
    } catch {
      this.setCandidateInvitationToken(null);
      this.setCandidateInvitationJobId(null);
    }
  }

  private mapJob(job: ApiJob, candidatesCount: number): Job {
    const assessmentWindow = (job.assessment_start_at && job.assessment_end_at)
      ? {
        startAt: job.assessment_start_at,
        endAt: job.assessment_end_at,
        timezone: job.assessment_timezone || 'UTC',
        slotMinutes: job.assessment_slot_minutes ?? 30,
      }
      : this.extractAssessmentWindow(job.jd_text);

    return {
      id: job.id,
      managerId: job.manager_user_id,
      title: job.title,
      department: job.department,
      location: job.location,
      employmentType: job.employment_type,
      seniority: job.seniority,
      status: this.mapJobStatus(job.status),
      description: job.description,
      requirements: job.requirements.map((requirement) => requirement.label),
      candidatesCount,
      postedAt: this.relativeTime(job.created_at),
      assessmentStartAt: assessmentWindow?.startAt,
      assessmentEndAt: assessmentWindow?.endAt,
      assessmentTimezone: assessmentWindow?.timezone,
      assessmentSlotMinutes: assessmentWindow?.slotMinutes,
      questionBlueprint: this.normalizeQuestionBlueprint(job.question_blueprint),
    };
  }

  buildAssessmentWebSocketUrl(relativePath: string): string {
    if (!relativePath) {
      return '';
    }

    const wsBase = this.apiBaseUrl.startsWith('https://')
      ? this.apiBaseUrl.replace('https://', 'wss://')
      : this.apiBaseUrl.replace('http://', 'ws://');

    const token = this.authService.accessToken();
    if (!token) {
      return `${wsBase}${relativePath}`;
    }

    const delimiter = relativePath.includes('?') ? '&' : '?';
    return `${wsBase}${relativePath}${delimiter}token=${encodeURIComponent(token)}`;
  }

  private mapAssessmentQuestionResult(item: AssessmentQuestionResult | Record<string, unknown>): AssessmentQuestionResult {
    const source = item as Record<string, unknown>;
    return {
      questionId: typeof source['questionId'] === 'string'
        ? source['questionId']
        : (typeof source['question_id'] === 'string' ? source['question_id'] : null),
      prompt: typeof source['prompt'] === 'string' ? source['prompt'] : null,
      stage: typeof source['stage'] === 'string' ? source['stage'] : null,
      answerText: typeof source['answerText'] === 'string'
        ? source['answerText']
        : (typeof source['answer_text'] === 'string' ? source['answer_text'] : null),
      answerTranscript: typeof source['answerTranscript'] === 'string'
        ? source['answerTranscript']
        : (typeof source['answer_transcript'] === 'string' ? source['answer_transcript'] : null),
      score: typeof source['score'] === 'number' ? source['score'] : null,
      confidence: typeof source['confidence'] === 'number' ? source['confidence'] : null,
      classification: typeof source['classification'] === 'string' ? source['classification'] : null,
      transcriptionModel: typeof source['transcriptionModel'] === 'string'
        ? source['transcriptionModel']
        : (typeof source['transcription_model'] === 'string' ? source['transcription_model'] : null),
      reasons: Array.isArray(source['reasons'])
        ? source['reasons'].map((entry) => `${entry}`)
        : [],
    };
  }

  private mapAntiSpoofStatus(response: ApiAntiSpoofStatusResponse): AntiSpoofStatus {
    return {
      status: String(response.status ?? '').trim() || 'unknown',
      finalDecision: response.final_decision ?? null,
      latestResultStatus: response.latest_result?.overall_status ?? null,
      latestSummary: response.latest_result?.human_readable_summary ?? null,
      trustScore: typeof response.trust_score === 'number' ? response.trust_score : null,
      retryCount: typeof response.retry_count === 'number' ? response.retry_count : 0,
      nextAction: response.next_action ?? null,
    };
  }

  private mapCandidate(candidate: ApiCandidateMatch, job: Job): Candidate {
    const email = candidate.candidate_email ?? `${candidate.candidate_external_id}@candidate.local`;
    const details = this.profileDetailsFromExplanation(candidate.explanation);
    const source = candidate.source === 'internal' || candidate.source === 'external'
      ? candidate.source
      : null;

    return {
      id: candidate.candidate_external_id || candidate.match_id,
      managerId: job.managerId,
      name: candidate.candidate_name,
      role: job.title,
      matchScore: Math.round(candidate.final_score),
      source,
      status: this.mapCandidateStatus(candidate.status),
      appliedAt: 'Recently',
      email,
      phone: 'Pending',
      experience: details.experience,
      education: details.education,
      skills: this.skillsFromRequirementAndExplanation(job.requirements, candidate.explanation),
      avatar: this.avatarForEmail(email),
      jobId: job.id,
      matchId: candidate.match_id,
    };
  }

  private mapScheduleSlot(slot: ApiScheduleSlot): ExamSlot {
    const start = new Date(slot.start_at);
    return {
      date: this.toLocalDateKey(start),
      time: start.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
      slotId: slot.id,
      timezone: slot.timezone,
      jobId: slot.job_id,
      startAt: slot.start_at,
      endAt: slot.end_at,
      capacity: slot.capacity,
      reservedCount: slot.reserved_count,
      isActive: slot.is_active,
    };
  }

  private mapInterviewSchedule(response: ApiInterviewScheduleResponse): InterviewScheduleResult {
    return {
      id: response.id,
      candidateProfileId: response.candidate_profile_id,
      jobId: response.job_id,
      slotId: response.slot_id,
      invitationToken: response.invitation_token,
      status: response.status,
      bookedAt: response.booked_at,
      cancelledAt: response.cancelled_at,
    };
  }

  private toLocalDateKey(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private mapJobStatus(status: ApiJobStatus): Job['status'] {
    switch (status) {
      case 'ACTIVE':
        return 'Active';
      case 'DRAFT':
        return 'Draft';
      case 'CLOSED':
        return 'Closed';
    }
  }

  private toApiJobStatus(status: Job['status']): ApiJobStatus {
    switch (status) {
      case 'Active':
        return 'ACTIVE';
      case 'Draft':
        return 'DRAFT';
      case 'Closed':
        return 'CLOSED';
    }
  }

  private mapCandidateStatus(status: ApiMatchStatus): Candidate['status'] {
    switch (status) {
      case 'MATCHED':
        return 'Screening';
      case 'SHORTLISTED':
        return 'Shortlisted';
      case 'INVITED':
        return 'Interview';
      case 'REJECTED':
        return 'Rejected';
      case 'HIRED':
        return 'Hired';
    }
  }

  private toApiMatchStatus(status: Candidate['status']): ApiMatchStatus {
    switch (status) {
      case 'Applied':
      case 'Screening':
        return 'MATCHED';
      case 'Shortlisted':
      case 'Offer':
        return 'SHORTLISTED';
      case 'Interview':
        return 'INVITED';
      case 'Rejected':
        return 'REJECTED';
      case 'Hired':
        return 'HIRED';
    }
  }

  private applyCandidateStatusLocally(id: string, status: Candidate['status']): void {
    this.allCandidates.update((candidates) => candidates.map((candidate) => candidate.id === id ? {...candidate, status} : candidate));
    this.candidatesByJob.update((byJob) => {
      const next: Record<string, Candidate[]> = {};
      for (const [jobId, candidates] of Object.entries(byJob)) {
        next[jobId] = candidates.map((candidate) => candidate.id === id ? {...candidate, status} : candidate);
      }
      return next;
    });
  }

  private toRequirementInputs(requirements: string[]): ApiJobCreateRequest['requirements'] {
    return requirements.map((requirement) => ({
      requirement_type: 'SKILL',
      label: requirement,
      weight: 1,
    }));
  }

  private areStringArraysEqual(left: string[], right: string[]): boolean {
    if (left.length !== right.length) {
      return false;
    }

    const normalize = (value: string) => value.trim().toLowerCase();
    const leftSorted = [...left].map(normalize).sort();
    const rightSorted = [...right].map(normalize).sort();

    return leftSorted.every((value, index) => value === rightSorted[index]);
  }

  private areQuestionBlueprintsEqual(left: QuestionBlueprintItem[] = [], right: QuestionBlueprintItem[] = []): boolean {
    if (left.length !== right.length) {
      return false;
    }

    return left.every((item, index) =>
      item.stage === right[index]?.stage
      && Number(item.count) === Number(right[index]?.count),
    );
  }

  private normalizeCandidateId(candidateId: string): string {
    try {
      return decodeURIComponent(candidateId);
    } catch {
      return candidateId;
    }
  }

  private syncJobCandidateCounts(): void {
    const byJob = this.candidatesByJob();
    this.allJobs.update((jobs) => jobs.map((job) => ({
      ...job,
      candidatesCount: byJob[job.id]?.length ?? 0,
    })));

    const merged = new Map<string, Candidate>();
    for (const candidates of Object.values(byJob)) {
      for (const candidate of candidates) {
        const existing = merged.get(candidate.id);
        if (!existing || candidate.matchScore > existing.matchScore) {
          merged.set(candidate.id, candidate);
        }
      }
    }
    this.allCandidates.set([...merged.values()]);
  }

  private buildJdText(
    description: string,
    requirements: string[],
  ): string {
    const lines = requirements.map((requirement) => `- ${requirement}`).join('\n');
    const text = `${description}\n\nRequirements:\n${lines}`.trim();

    if (text.length >= 40) {
      return text;
    }
    return `${text}\n\nAdditional role details will be shared during screening.`;
  }

  private extractAssessmentWindow(jdText: string): {startAt: string; endAt: string; timezone: string; slotMinutes: number} | null {
    const match = jdText.match(/\[ASSESSMENT_WINDOW\]([\s\S]*?)\[\/ASSESSMENT_WINDOW\]/i);
    if (!match) {
      return null;
    }

    const fields: Record<string, string> = {};
    for (const rawLine of match[1].split('\n')) {
      const line = rawLine.trim();
      if (!line || !line.includes('=')) {
        continue;
      }
      const [key, value] = line.split('=', 2);
      fields[key.trim().toLowerCase()] = value.trim();
    }

    const startAt = fields['start'];
    const endAt = fields['end'];
    if (!startAt || !endAt) {
      return null;
    }

    const timezone = fields['timezone'] || 'UTC';
    const slotMinutesRaw = Number(fields['slot_minutes'] || '30');
    const slotMinutes = Number.isFinite(slotMinutesRaw)
      ? Math.max(5, Math.min(180, Math.trunc(slotMinutesRaw)))
      : 30;

    return {
      startAt,
      endAt,
      timezone,
      slotMinutes,
    };
  }

  private normalizeAssessmentWindow(
    window?: {startAt?: string; endAt?: string; timezone?: string; slotMinutes?: number},
  ): {startAt: string; endAt: string; timezone: string; slotMinutes: number} | null {
    const startRaw = window?.startAt?.trim();
    const endRaw = window?.endAt?.trim();
    if (!startRaw || !endRaw) {
      return null;
    }

    const start = new Date(startRaw);
    const end = new Date(endRaw);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
      return null;
    }

    const timezone = window?.timezone?.trim() || 'UTC';
    const slotMinutesRaw = Number(window?.slotMinutes ?? 30);
    const slotMinutes = Number.isFinite(slotMinutesRaw)
      ? Math.max(5, Math.min(180, Math.trunc(slotMinutesRaw)))
      : 30;

    return {
      startAt: start.toISOString(),
      endAt: end.toISOString(),
      timezone,
      slotMinutes,
    };
  }

  private normalizeQuestionBlueprint(
    blueprint?: QuestionBlueprintItem[] | null,
  ): QuestionBlueprintItem[] {
    if (!Array.isArray(blueprint) || blueprint.length === 0) {
      return [
        {stage: 'INTRO', count: 1},
        {stage: 'CANDIDATE_INFO', count: 1},
        {stage: 'ROLE_SPECIFIC', count: 10},
        {stage: 'CODING', count: 2},
        {stage: 'SUMMARY', count: 1},
      ];
    }

    return blueprint
      .filter((item) => item && typeof item.stage === 'string' && Number(item.count) > 0)
      .map((item) => ({
        stage: item.stage,
        count: Math.max(1, Math.min(20, Math.trunc(Number(item.count) || 1))),
      }));
  }

  private skillsFromRequirementAndExplanation(requirements: string[], explanation: string): string[] {
    const fromExplanation = explanation
      .split(/[|,]/g)
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
      .slice(0, 4);

    if (fromExplanation.length > 0) {
      return fromExplanation;
    }

    const required = requirements.slice(0, 4);
    if (required.length > 0) {
      return required;
    }

    return ['General aptitude'];
  }

  private profileDetailsFromExplanation(explanation: string): {experience: string; education: string} {
    const normalized = explanation.trim();
    if (!normalized) {
      return {
        experience: 'Under review',
        education: 'Under review',
      };
    }

    const signals = normalized
      .split('|')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);

    const years = normalized.match(/(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:years?|yrs?)/i);
    const experienceSignal = signals.find((item) => /(experience|years?|yrs?)/i.test(item));
    const educationSignal = signals.find((item) => /(education|bachelor|master|phd|degree|university|college)/i.test(item));

    return {
      experience: years ? `${years[1]} years` : (experienceSignal ?? 'Under review'),
      education: educationSignal ?? 'Under review',
    };
  }

  private resolveOrchestrationBaseUrl(): string {
    const envValue = (globalThis as {ORCHESTRATION_API_BASE_URL?: string}).ORCHESTRATION_API_BASE_URL;
    if (envValue) {
      return envValue;
    }

    if (typeof localStorage !== 'undefined') {
      const persisted = localStorage.getItem('talentos.orchestration.baseUrl');
      if (persisted) {
        return persisted;
      }
    }

    return 'http://127.0.0.1:8001';
  }

  private avatarForEmail(email: string): string {
    const seed = encodeURIComponent(email.toLowerCase());
    return `https://api.dicebear.com/9.x/notionists/svg?seed=${seed}`;
  }

  private relativeTime(isoDate: string): string {
    const target = new Date(isoDate);
    const now = new Date();
    const diffMs = now.getTime() - target.getTime();
    const diffHours = Math.max(1, Math.floor(diffMs / (1000 * 60 * 60)));

    if (diffHours < 24) {
      return `${diffHours}h ago`;
    }

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) {
      return `${diffDays}d ago`;
    }

    return target.toLocaleDateString();
  }

  private extractErrorMessage(error: unknown, fallback: string): string {
    const candidate = error as {
      error?: {
        error?: {
          message?: string;
        };
        detail?: unknown;
      };
      message?: string;
    };

    const apiMessage = candidate.error?.error?.message;
    if (apiMessage) {
      return apiMessage;
    }

    const detail = candidate.error?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim();
    }
    if (Array.isArray(detail)) {
      for (const item of detail) {
        const msg = (item as {msg?: unknown})?.msg;
        if (typeof msg === 'string' && msg.trim()) {
          return msg.trim();
        }
      }
    }

    if (candidate.message) {
      return candidate.message;
    }

    return fallback;
  }

  private httpStatusCode(error: unknown): number | null {
    const candidate = error as {status?: unknown};
    return typeof candidate.status === 'number' ? candidate.status : null;
  }

  private resetState(): void {
    this.allJobs.set([]);
    this.allCandidates.set([]);
    this.candidatesByJob.set({});
    this.errorMessage.set(null);
    this.loading.set(false);
    this.scheduledExam.set(null);
    this.examCompleted.set(false);
    this.examScore.set(null);
    this.availableExamSlots.set([]);
    this.candidateSchedules.set([]);
    this.candidateInvitationToken.set(null);
    this.candidateInvitationJobId.set(null);
  }
}
