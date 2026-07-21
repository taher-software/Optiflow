import { createNativeStackNavigator } from "@react-navigation/native-stack";

import type { RootStackParamList } from "../constants/routes";
import { DeclareDownTimeScreen } from "../screens/DeclareDownTimeScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { IssueDetailScreen } from "../screens/IssueDetailScreen";
import { IssueListScreen } from "../screens/IssueListScreen";
import { ProspectScreen } from "../screens/ProspectScreen";
import { SecurityCodeScreen } from "../screens/SecurityCodeScreen";

const Stack = createNativeStackNavigator<RootStackParamList>();

/** Root navigation stack: Prospect → SecurityCode → Home. */
export function AppNavigator() {
  return (
    <Stack.Navigator
      initialRouteName="Prospect"
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: "#020617" },
      }}
    >
      <Stack.Screen name="Prospect" component={ProspectScreen} />
      <Stack.Screen name="SecurityCode" component={SecurityCodeScreen} />
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="IssueList" component={IssueListScreen} />
      <Stack.Screen name="IssueDetail" component={IssueDetailScreen} />
      <Stack.Screen name="DeclareDownTime" component={DeclareDownTimeScreen} />
    </Stack.Navigator>
  );
}

export default AppNavigator;
