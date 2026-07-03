export async function POST(request: Request) {
  const body = await request.formData();
  const baseUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace("/api/v1", "") || "http://localhost:8001"}`;
  const response = await fetch(`${baseUrl}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      username: body.get('username') as string,
      password: body.get('password') as string,
    }),
  });
  const data = await response.json();
  return Response.json(data);
}
