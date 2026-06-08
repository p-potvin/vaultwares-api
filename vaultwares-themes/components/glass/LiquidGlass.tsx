/// <reference types="@react-three/fiber" />
import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import type { RootState } from '@react-three/fiber'
import { MeshTransmissionMaterial, Environment, RoundedBox, Float } from '@react-three/drei'
import * as THREE from 'three'

function LiquidShape() {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((state: RootState) => {
    if (meshRef.current) {
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.5) * 0.2
      meshRef.current.rotation.y += 0.01
    }
  })

  return (
    <Float floatIntensity={2} speed={2}>
      <RoundedBox ref={meshRef} args={[2.5, 2.5, 0.4]} radius={0.2} smoothness={4} position={[0, 0, 0]}>
        <MeshTransmissionMaterial
          background={new THREE.Color('#fdf6e3')}
          thickness={0.5}
          roughness={0.05}
          transmission={1}
          ior={1.4}
          chromaticAberration={0.05}
          distortion={0.2}
          distortionScale={0.3}
          temporalDistortion={0.1}
        />
      </RoundedBox>
    </Float>
  )
}

function FloatingOrbs() {
  return (
    <>
      <mesh position={[-2, -1, -2]}>
        <sphereGeometry args={[0.5, 32, 32]} />
        <meshStandardMaterial color="#cb4b16" roughness={0.2} />
      </mesh>
      <mesh position={[2, 1, -3]}>
        <sphereGeometry args={[0.8, 32, 32]} />
        <meshStandardMaterial color="#268bd2" roughness={0.2} />
      </mesh>
      <mesh position={[0, 0, -4]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#859900" roughness={0.2} />
      </mesh>
    </>
  )
}

export const LiquidGlassEffect = () => {
  return (
    <div className="w-full h-96 relative overflow-hidden rounded-2xl bg-[#eee8d5] border border-[#93a1a1]/20 shadow-inner flex items-center justify-center">
      <div className="absolute inset-0 z-0 flex items-center justify-center pointer-events-none">
        <h2 className="text-6xl font-bold text-[#93a1a1] opacity-20 select-none">iOS 26 Liquid</h2>
      </div>
      <div className="absolute inset-0 z-10 pointer-events-none">
        <Canvas camera={{ position: [0, 0, 4] }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          <FloatingOrbs />
          <LiquidShape />
          <Environment preset="city" />
        </Canvas>
      </div>
    </div>
  )
}
