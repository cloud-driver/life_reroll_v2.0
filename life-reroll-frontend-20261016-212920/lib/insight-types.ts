export type Radar = {
  run_id: string;
  run_version: number;
  as_of: string;
  level: 'LOW' | 'WATCH' | 'HIGH';
  facts: string[];
  method: 'MODEL' | 'RULES';
  model_version: string;
  horizon_months: number;
  metrics: {
    liquidity_minor: number;
    monthly_burden_minor: number;
    monthly_income_minor: number;
    reserve_months: number;
    monthly_gap_minor: number;
    bill_minor: number;
    loan_monthly_minor: number;
    annual_premium_minor: number;
  };
  validation: null | { training_samples: number; validation_samples: number; balanced_accuracy: number };
};
type Range = { low: number; median: number; high: number };
export type BranchVariant = {
  samples: number;
  shortage_count: number;
  ended_early_count: number;
  net_change_minor: Range;
  minimum_liquidity_minor: Range;
  quality: Range;
  duration_months: { min: number; max: number };
};
export type BranchResult = { point_id: string; variants: { CURRENT: BranchVariant; BASIC: BranchVariant } };
export type BranchJob = {
  id: string;
  run_id: string;
  run_version: number;
  campaign_version: number;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'CANCELLED' | 'FAILED';
  completed_points: number;
  total_points: number;
  results: BranchResult[];
  horizon_months: number;
  samples: number;
  notice: string;
  created_at: string;
  method_version: string;
};
