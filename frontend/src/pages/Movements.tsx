import React, { useState, useEffect } from 'react';
import { DateMovementPanel } from '../components/DateMovementPanel';
import { Movement } from '../types';
import { apiClient } from '../api/client';
import { SourceSelector } from '../components/SourceSelector';

interface MovementsProps {
  refreshKey?: string | null;
  selectedSource?: string;
  onSourceChange?: (source: string) => void;
}

export const Movements: React.FC<MovementsProps> = ({
  refreshKey,
  selectedSource = 'active',
  onSourceChange,
}) => {
  const [movements, setMovements] = useState<Movement[]>([]);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [productFilter, setProductFilter] = useState('');
  const [movementType, setMovementType] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    apiClient.getMovements({
      product_id: productFilter,
      from_date: fromDate,
      to_date: toDate,
      movement_type: movementType,
      source: selectedSource,
    })
      .then((res) => setMovements(res.items))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [fromDate, toDate, productFilter, movementType, refreshKey, selectedSource]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Daily Stock Movement Registers</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Chronological daily Inward (Receipts) and Outward (Dispatches) transactions across all sources
          </p>
        </div>
        {onSourceChange && (
          <SourceSelector
            value={selectedSource}
            onChange={onSourceChange}
          />
        )}
      </div>

      <DateMovementPanel
        movements={movements}
        fromDate={fromDate}
        toDate={toDate}
        onFromDateChange={setFromDate}
        onToDateChange={setToDate}
        productFilter={productFilter}
        onProductFilterChange={setProductFilter}
        movementType={movementType}
        onMovementTypeChange={setMovementType}
      />
    </div>
  );
};
