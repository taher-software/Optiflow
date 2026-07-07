import "./global.css";

import { StatusBar } from "expo-status-bar";

import { SplashScreen } from "./src/screens/SplashScreen";

export default function App() {
  return (
    <>
      <StatusBar style="light" />
      <SplashScreen />
    </>
  );
}
