import { STATUS_LABEL, statusTone } from '../utils/format';
import type { VerificationStatus } from '../types';

export function StatusBadge({ status }: { status: VerificationStatus }) {
  return <span className={`badge badge-${statusTone(status)}`}>{STATUS_LABEL[status]}</span>;
}

export default StatusBadge;
