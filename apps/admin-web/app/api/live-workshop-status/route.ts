export async function GET() {
  const baseUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace("/api/v1", "") || "http://localhost:8001"}`;
  const response = await fetch(`${baseUrl}/api/v1/analytics/dashboard/live-workshop-status`);
  const data = await response.json();
  return Response.json(data);
}
