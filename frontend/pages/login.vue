<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useLoginPreferenceStore } from "~/stores/useLoginPreferenceStore";

definePageMeta({
  layout: "blank",
});

// login preference
const loginPreferenceStore = useLoginPreferenceStore();
const { loginPreference } = storeToRefs(loginPreferenceStore);

const switchLoginPreference = () => {
  loginPreferenceStore.setLoginPreference(
    loginPreference.value === "password" ? "code" : "password"
  );
};

// password login
const username = ref("");
const password = ref("");

const { loading, error, login } = await useLoginApi(username, password);

watch(error, (newError) => {
  if (newError) {
    ElMessage.error("登录失败");
  }
});

const onLoginButtonClicked = async () => {
  await login();
  if (error.value === false) {
    navigateTo("/");
    ElMessage.success("登录成功");
  }
};

// bot login

const {
  code: loginCode,
  timeout: loginCodeTimeout,
  countdown: loginCodeCountdown,
  success: codeLoginSuccess,
  open: receiveLoginCode,
  close: closeCodeLoginWS,
} = useCodeLoginApi();

const copyLoginCode = () => {
  navigator.clipboard.writeText(loginCode.value);
  ElMessage.success("复制成功");
};

watchEffect(() => {
  if (loginPreference.value === "code") {
    receiveLoginCode();
  } else {
    closeCodeLoginWS();
  }
});

watch(codeLoginSuccess, (newCodeLoginSuccess) => {
  if (newCodeLoginSuccess) {
    navigateTo("/");
    ElMessage.success("登录成功");
  }
});
</script>

<template>
  <div class="flex justify-center items-center h-screen">
    <div class="w-96">
      <ElCard class="shadow-lg">
        <div class="login-card-content flex flex-col items-center">
          <h1 class="text-2xl font-bold mb-4">登录</h1>
          <ElForm v-if="loginPreference === 'password'" class="w-full">
            <ElFormItem label="用户名" label-width="70">
              <ElInput v-model="username" name="username" />
            </ElFormItem>
            <ElFormItem label="密码" label-width="70">
              <ElInput v-model="password" type="password" name="password" />
            </ElFormItem>
            <ElFormItem>
              <div class="form-button w-full flex gap-8">
                <ElButton class="flex-1" @click="switchLoginPreference"
                  >机器人登录</ElButton
                >
                <ElButton
                  class="flex-1"
                  type="primary"
                  @click="onLoginButtonClicked"
                  :loading="loading"
                  >登录</ElButton
                >
              </div>
            </ElFormItem>
          </ElForm>
          <ElForm v-else class="w-full">
            <ElFormItem label="动态码" label-width="70">
              <div class="flex flex-col items-center w-full">
                <span>{{ loginCode }}</span>
                <ElProgress
                  :show-text="false"
                  :stroke-width="2"
                  :percentage="(loginCodeCountdown / loginCodeTimeout) * 100"
                  class="w-full"
                />
              </div>
            </ElFormItem>
            <ElFormItem>
              <div class="form-button w-full flex gap-8">
                <ElButton class="flex-1" @click="switchLoginPreference"
                  >密码登录</ElButton
                >
                <ElButton class="flex-1" type="primary" @click="copyLoginCode"
                  >复制</ElButton
                >
              </div>
            </ElFormItem>
          </ElForm>
        </div>
      </ElCard>
    </div>
  </div>
</template>
