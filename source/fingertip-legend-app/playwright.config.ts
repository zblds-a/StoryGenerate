import {defineConfig} from '@playwright/test'
export default defineConfig({
 testDir:'./e2e',workers:1,timeout:60000,fullyParallel:false,
 use:{actionTimeout:10000,baseURL:'http://127.0.0.1:5193',headless:true,trace:'retain-on-failure',screenshot:'only-on-failure',
  launchOptions:process.env.STORY_TEST_BROWSER?{executablePath:process.env.STORY_TEST_BROWSER}:{}},
 outputDir:'evidence/playwright',reporter:[['list'],['html',{outputFolder:'evidence/browser-report',open:'never'}]],
 webServer:[
  {command:`"${process.env.STORY_TEST_PYTHON||'python'}" scripts/story_e2e_server.py`,url:'http://127.0.0.1:5194/health',reuseExistingServer:false},
  {command:'npm run dev:h5',url:'http://127.0.0.1:5193',reuseExistingServer:false,timeout:90000,env:{VITE_USE_MOCK:'false',VITE_API_BASE_URL:'http://127.0.0.1:5194/api/v1'}}
 ]
})
