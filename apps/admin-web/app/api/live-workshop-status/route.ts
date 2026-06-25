export async function GET() {
  const response = await fetch('http://localhost:8001/api/v1/analytics/dashboard/live-workshop-status');
  const data = await response.json();
  return Response.json(data);
}
