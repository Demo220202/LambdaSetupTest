pipeline {
    agent any
//     agent { label 'master' }

//     environment {
// //         SONAR_API_TOKEN = credentials('sonar-api-token')
//         GITHUB_TOKEN    = credentials('GH_PAT_WITH_ACCESS_TO_OTHER_REPOS')
//         PATH = "/opt/homebrew/bin:/usr/local/bin:${env.PATH}"
//     }

    stages {

        stage('Step 0: VPC Listing') {
            steps {

                sh """
                    python3 -m venv venvlambda
                    . venvlambda/bin/activate
                    pip install -r requirements.txt
                    python lambdaCreationAutomationAllEnvs3.py --phase vpc_listing
                """
            }
        }

        stage('Step 1: VPC Selection') {
            steps {

                script {
                    def vpcId = input(
                        id: 'firstInput',
                        message: 'Paste the VPC ids',
                        parameters: [
                            text(name: 'VPC_ID', description: 'Enter VPC ids')
                        ]
                    )

                    env.VPC_ID = vpcId.toString()
                }

                sh """

                    . venvlambda/bin/activate
                    pip install -r requirements.txt
                    python lambdaCreationAutomationAllEnvs3.py --phase vpc_selection
                """
            }
        }

        stage('Step 2: Subnets ids Listing') {
            steps {

                sh """
                    . venvlambda/bin/activate
                    python lambdaCreationAutomationAllEnvs3.py \
                        --phase subnet_listing
                """
            }
        }

        stage('Step 3: Subnets ids Selection') {
            steps {
                script {
                    def subnetIds = input(
                        id: 'secondInput',
                        message: 'Paste the Subnet ids',
                        parameters: [
                            text(name: 'SUBNET_IDS', description: 'Enter Subnet ids')
                        ]
                    )

                    env.COMMON_SUBNETS = subnetIds.toString()
                }

                script {
                    def subnetIds = input(
                        id: 'secondInput',
                        message: 'Paste the Subnet ids',
                        parameters: [
                            text(name: 'SUBNET_IDS', description: 'Enter Subnet ids')
                        ]
                    )

                    env.UAT_SUBNETS = subnetIds.toString()
                }

                script {
                    def subnetIds = input(
                        id: 'secondInput',
                        message: 'Paste the Subnet ids',
                        parameters: [
                            text(name: 'SUBNET_IDS', description: 'Enter Subnet ids')
                        ]
                    )

                    env.DR_SUBNETS = subnetIds.toString()
                }

                sh """
                    . venvlambda/bin/activate
                    python lambdaCreationAutomationAllEnvs3.py \
                        --phase subnet_selection
                """
            }
        }

        stage('Step 4: Approval for Lambda Creation') {
            steps {
                script {
                    // Only waits for human approval
                    def approval = input(
                        id: 'approvalInput',
                        message: 'Do you want to proceed with lambda setup?',
                        parameters: [
                            choice(name: 'PROCEED', choices: ['Yes', 'No'], description: 'Select Yes to continue')
                        ]
                    )

                    if (approval == 'No') {
                        error "Lambda setup aborted by user."
                    }
                }


                sh """
                    . venvlambda/bin/activate
                    python lambdaCreationAutomationAllEnvs3.py --lambda_name '$lambda_name' --runtime '$runtime' --role_name '$role_name' --memory $memory --timeout $timeout --ephemeral_storage $ephemeral_storage --layers '$layers' --enable_reserved_concurrency $enable_reserved_concurrency --reserved_concurrency '$reserved_concurrency' --phase finalize
                """

            }
        }

    }
}
