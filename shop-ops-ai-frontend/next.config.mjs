/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      { source: '/login', destination: '/' },
      { source: '/dashboard', destination: '/' },
      { source: '/dashboard/:path*', destination: '/' },
    ]
  },
}

export default nextConfig
