'use client';

import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface UtilizationData {
  gate_to_advisor_minutes: number;
  advisor_to_technician_minutes: number;
  total_turnaround_minutes: number;
  capture_compliance_percent: number;
  bottleneck_stages: string[];
}

export default function AnalyticsPage() {
  const [data, setData] = useState<UtilizationData | null>(null);

  useEffect(() => {
    fetchMetrics();
  }, []);

  const fetchMetrics = async () => {
    try {
      const response = await fetch('/api/analytics/utilization');
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
    }
  };

  const chartData = data ? [
    { name: 'Gate → Advisor', time: data.gate_to_advisor_minutes || 0 },
    { name: 'Advisor → Tech', time: data.advisor_to_technician_minutes || 0 },
    { name: 'Total TAT', time: data.total_turnaround_minutes || 0 },
  ] : [];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Workshop Analytics</h1>
      
      {data ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-blue-50 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Compliance Rate</p>
              <p className="text-2xl font-bold">{data.capture_compliance_percent}%</p>
            </div>
            
            <div className="bg-yellow-50 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Total Turnaround</p>
              <p className="text-2xl font-bold">{data.total_turnaround_minutes} min</p>
            </div>
            
            <div className="bg-red-50 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Bottlenecks</p>
              <p className="text-sm">{data.bottleneck_stages.join(', ') || 'None detected'}</p>
            </div>
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="time" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <p>Loading metrics...</p>
      )}
    </div>
  );
}