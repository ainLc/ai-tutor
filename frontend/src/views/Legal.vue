<template>
  <main class="legal">
    <div class="container">
      <p class="kicker">合上资料仍会</p>
      <h1 class="display">{{ title }}</h1>
      <p class="updated">最近更新：2026-09-11</p>

      <article v-if="doc === 'privacy'">
        <p>我们收的是「你会并且还记得」这件事的操作系统，不是你的资料本身要拿去训练公开模型。</p>
        <h2>我们处理什么</h2>
        <ul>
          <li>账号：用户名、昵称、密码哈希。</li>
          <li>你上传的学习资料，以及由此拆出的课、讲解、卡片、答辩记录。</li>
          <li>你在设置里填写的模型密钥（只存本账号，接口不再明文返回）。</li>
        </ul>
        <h2>默认私有</h2>
        <p>资料与记忆进度默认仅你可见。分享课只复制结构，记忆进度永不复制。团队空间若上线，必须显式邀请。</p>
        <h2>删除</h2>
        <p>设置页删除账号后，课、卡、复习日志、答辩、密钥一并删除，不可恢复。</p>
        <h2>密钥</h2>
        <p>日志禁止打印 Key。页面只显示掩码。你也可以只用服务器 .env 里的托管 Key（付费档才应提供）。</p>
      </article>

      <article v-else>
        <p>使用本产品即表示：你保证对上传资料拥有相应授权。投诉盗版教材，我们将停用该课。</p>
        <h2>产品承诺</h2>
        <ul>
          <li>没有「已完成」。只有已理解 / 已学过尚未记住 / 已记住。</li>
          <li>不懂不能把进度写成学完。合上书答辩通过才出具可对外的凭证。</li>
          <li>体验套餐凭证带水印，不作为对公正式证明。</li>
        </ul>
        <h2>负荷熔断</h2>
        <p>今日到期超过 40 张时默认锁定新课。强行继续需勾选「我知道这会降低 14 日保持率」。</p>
        <h2>掌握保险（C1，尚未生效赔付）</h2>
        <p>规则预告：依从率过低不触发顺延；只顺延学习时间，不退现金。</p>
        <h2>免责</h2>
        <p>讲解可能出错。发现「不在资料里」请举报。凭证证明的是提取记录，不是学历或职业资格。</p>
      </article>

      <p class="back"><router-link to="/login">返回登录</router-link> · <router-link to="/">今日</router-link></p>
    </div>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const doc = computed(() => route.params.doc === 'terms' ? 'terms' : 'privacy')
const title = computed(() => doc.value === 'terms' ? '使用条款' : '隐私政策')
</script>

<style scoped>
.legal { padding: 48px 0 80px; }
.kicker { color: var(--brand); font-size: 12px; font-weight: 600; margin: 0 0 8px; }
h1 { font-size: 32px; margin: 0 0 8px; }
.updated { color: var(--text-secondary); font-size: 13px; }
article { max-width: 680px; background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 28px; box-shadow: var(--shadow); }
h2 { font-size: 17px; margin: 24px 0 8px; }
.back { margin-top: 24px; color: var(--text-secondary); }
</style>
