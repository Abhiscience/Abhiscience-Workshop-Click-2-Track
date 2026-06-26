export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const token = formData.get('token') as string;
    const stage_id = formData.get('stage_id') as string || '1';
    const image = formData.get('image');

    const fd = new FormData();
    if (image) fd.append('image', image as Blob);

    const response = await fetch(
      `http://76.13.223.20:8001/api/v1/captures/?stage_id=${stage_id}`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      }
    );

    if (!response.ok) {
      const text = await response.text();
      return Response.json({ error: text }, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
  } catch (err: any) {
    return Response.json({ error: err.message || 'Unknown error' }, { status: 500 });
  }
}
