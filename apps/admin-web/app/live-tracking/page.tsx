'use client';

import { useEffect, useState } from 'react';

interface VehicleStatus {
  job_card_id: string;
  registration: string;
  current_stage: string;
  entered_at: string;
}

export default function LiveTrackingPage() {
  const [vehicles, setVehicles] = useState<VehicleStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLiveStatus();
    const interval = setInterval(fetchLiveStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchLiveStatus = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/live-workshop-status');
      const data = await response.json();
      setVehicles(data.active_vehicles || []);
    } catch (error) {
      console.error('Failed to fetch live status:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Live Workshop Tracking</h1>
      
      {loading ? (
        <p>Loading...</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {vehicles.map((v) => (
            <div key={v.job_card_id} className="border rounded-lg p-4 shadow-sm">
              <h3 className="font-bold">{v.registration}</h3>
              <p className="text-sm text-gray-600">Job Card: {v.job_card_id}</p>
              <p className="text-sm">Stage: {v.current_stage}</p>
              <p className="text-sm">Entered: {new Date(v.entered_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}