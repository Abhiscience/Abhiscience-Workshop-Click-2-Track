module.exports = {
  apps: [
    {
      name: 'workshop-api',
      cwd: '/root/Abhiscience-Workshop-Click-2-Track/services/api',
      script: './.venv/bin/uvicorn',
      args: 'app.main:app --host 0.0.0.0 --port 8000 --reload',
      interpreter: '/root/Abhiscience-Workshop-Click-2-Track/services/api/.venv/bin/python',
      env: {
        PATH: '/root/Abhiscience-Workshop-Click-2-Track/services/api/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        PYTHONPATH: '/root/Abhiscience-Workshop-Click-2-Track/services/api:/root/Abhiscience-Workshop-Click-2-Track/packages/anpr-providers:/root/Abhiscience-Workshop-Click-2-Track/packages/workflow-engine',
      },
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
    },
    {
      name: 'workshop-web',
      cwd: '/root/Abhiscience-Workshop-Click-2-Track/apps/admin-web',
      script: './node_modules/.bin/next',
      args: 'start',
      env: {
        PATH: '/root/Abhiscience-Workshop-Click-2-Track/apps/admin-web/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        NEXT_PUBLIC_API_URL: 'http://76.13.223.20:8000/api/v1',
      },
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
    },
  ],
};
